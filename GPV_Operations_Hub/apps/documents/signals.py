"""Register document job handlers and file access through documents."""
from apps.core.permissions import register_file_access_hook

from . import services  # noqa: F401


@register_file_access_hook
def preview_file_access(user, stored_file):
    # preview PDFs follow the visibility of their source document
    parent = stored_file.parent
    if parent is not None and stored_file.original_name.startswith("vista_previa_"):
        from apps.core.permissions import can_access_file

        return can_access_file(user, parent)
    return False
