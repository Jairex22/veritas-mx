"""Windows integrated authentication (SSPI) using only the Python standard library.

This talks to the Windows Security Support Provider Interface (``Secur32.dll``) through
``ctypes`` to obtain Negotiate/NTLM tokens for the **currently logged-on user**. It lets the
application authenticate to an internal server as the operator themselves — the same mechanism
a browser or Excel uses against a Windows-authenticated endpoint.

Properties relevant for this project:
* No external package is installed (no ``pip``), no administrator rights.
* The user's password is never read, requested or stored: SSPI uses the existing logon session's
  default credentials. The tokens produced are opaque and single-use.
* Works only on Windows. ``sspi_available()`` returns ``False`` elsewhere (e.g. the Linux CI),
  so the rest of the app falls back to anonymous requests and the unit tests do not need SSPI.

Only the token handshake is implemented here; the HTTP side lives in ``odata_client`` so it reuses
the same bounded-read, redirect-block and size-limit protections as the anonymous transport.
"""
from __future__ import annotations

import sys

# SSPI return codes.
SEC_E_OK = 0x00000000
SEC_I_CONTINUE_NEEDED = 0x00090312
SEC_I_COMPLETE_NEEDED = 0x00090313
SEC_I_COMPLETE_AND_CONTINUE = 0x00090314

_SECPKG_CRED_OUTBOUND = 0x00000002
_SECURITY_NATIVE_DREP = 0x00000010
_SECBUFFER_TOKEN = 0x00000002
_SECBUFFER_VERSION = 0x00000000
# Ask SSPI to allocate the output buffer and keep the context connection-bound (NTLM needs this).
_ISC_REQ_ALLOCATE_MEMORY = 0x00000100
_ISC_REQ_CONNECTION = 0x00000800
_ISC_FLAGS = _ISC_REQ_ALLOCATE_MEMORY | _ISC_REQ_CONNECTION


class SspiError(Exception):
    """An SSPI call failed. ``status`` holds the raw SECURITY_STATUS when available."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def sspi_available() -> bool:
    """True only on Windows with a usable Secur32.dll."""
    if sys.platform != "win32":
        return False
    try:  # pragma: no cover - exercised only on Windows
        import ctypes

        ctypes.WinDLL("Secur32.dll")
        return True
    except Exception:  # noqa: BLE001 - any failure means "not available"
        return False


# Everything below touches Windows-only APIs; it is imported lazily and skipped off Windows.
if sys.platform == "win32":  # pragma: no cover - requires Windows SSPI
    import ctypes
    from ctypes import POINTER, byref, c_ulong, c_void_p, c_wchar_p

    _secur32 = ctypes.WinDLL("Secur32.dll")

    class _SecurityInteger(ctypes.Structure):
        _fields_ = [("LowPart", ctypes.c_ulong), ("HighPart", ctypes.c_long)]

    class _SecHandle(ctypes.Structure):
        _fields_ = [("lower", c_void_p), ("upper", c_void_p)]

    class _SecBuffer(ctypes.Structure):
        _fields_ = [("cbBuffer", c_ulong), ("BufferType", c_ulong), ("pvBuffer", c_void_p)]

    class _SecBufferDesc(ctypes.Structure):
        _fields_ = [("ulVersion", c_ulong), ("cBuffers", c_ulong), ("pBuffers", POINTER(_SecBuffer))]

    _AcquireCredentialsHandle = _secur32.AcquireCredentialsHandleW
    _AcquireCredentialsHandle.restype = ctypes.c_long
    _InitializeSecurityContext = _secur32.InitializeSecurityContextW
    _InitializeSecurityContext.restype = ctypes.c_long
    _FreeCredentialsHandle = _secur32.FreeCredentialsHandle
    _DeleteSecurityContext = _secur32.DeleteSecurityContext
    _FreeContextBuffer = _secur32.FreeContextBuffer

    class _WindowsSspiClient:
        """One authentication handshake against a single target, as the logged-on user."""

        def __init__(self, package: str, target_spn: str) -> None:
            self.package = package
            self.target_spn = target_spn
            self.complete = False
            self._cred = _SecHandle()
            self._ctx = _SecHandle()
            self._have_ctx = False
            expiry = _SecurityInteger()
            status = _AcquireCredentialsHandle(None, c_wchar_p(package), _SECPKG_CRED_OUTBOUND,
                                               None, None, None, None, byref(self._cred), byref(expiry))
            if status < 0:
                raise SspiError(f"AcquireCredentialsHandle({package}) failed", status)

        def _step(self, challenge: bytes | None) -> bytes:
            out_buf = _SecBuffer(0, _SECBUFFER_TOKEN, None)
            out_desc = _SecBufferDesc(_SECBUFFER_VERSION, 1, ctypes.pointer(out_buf))
            in_desc_ref = None
            in_storage = None
            if challenge:
                in_storage = ctypes.create_string_buffer(challenge, len(challenge))
                in_buf = _SecBuffer(len(challenge), _SECBUFFER_TOKEN, ctypes.cast(in_storage, c_void_p))
                in_desc = _SecBufferDesc(_SECBUFFER_VERSION, 1, ctypes.pointer(in_buf))
                in_desc_ref = byref(in_desc)
            attrs = c_ulong(0)
            expiry = _SecurityInteger()
            ctx_in = byref(self._ctx) if self._have_ctx else None
            status = _InitializeSecurityContext(
                byref(self._cred), ctx_in, c_wchar_p(self.target_spn), _ISC_FLAGS, 0, _SECURITY_NATIVE_DREP,
                in_desc_ref, 0, byref(self._ctx), byref(out_desc), byref(attrs), byref(expiry))
            _ = in_storage  # keep the input buffer alive until the call returns
            if status < 0:
                raise SspiError("InitializeSecurityContext failed", status)
            self._have_ctx = True
            if status in (SEC_E_OK, SEC_I_COMPLETE_NEEDED):
                self.complete = True
            token = b""
            if out_buf.pvBuffer and out_buf.cbBuffer:
                token = ctypes.string_at(out_buf.pvBuffer, out_buf.cbBuffer)
                _FreeContextBuffer(out_buf.pvBuffer)
            return token

        def first_token(self) -> bytes:
            return self._step(None)

        def next_token(self, challenge: bytes) -> bytes:
            return self._step(challenge)

        def close(self) -> None:
            if self._have_ctx:
                _DeleteSecurityContext(byref(self._ctx))
                self._have_ctx = False
            _FreeCredentialsHandle(byref(self._cred))


def make_client(package: str, target_spn: str):
    """Create an SSPI handshake client for ``package`` ("Negotiate"/"NTLM") and target SPN.

    Raises ``SspiError`` if SSPI is not available on this platform.
    """
    if sys.platform != "win32":
        raise SspiError("SSPI is only available on Windows")
    return _WindowsSspiClient(package, target_spn)  # pragma: no cover - Windows only
