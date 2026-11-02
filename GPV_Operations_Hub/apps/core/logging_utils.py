"""Operation id propagation for logs."""
import contextvars
import logging
import uuid

_op_id = contextvars.ContextVar("gpv_op_id", default="-")


def new_op_id():
    return uuid.uuid4().hex[:12]


def set_op_id(value):
    return _op_id.set(value)


def get_op_id():
    return _op_id.get()


def reset_op_id(token):
    _op_id.reset(token)


class OperationIdFilter(logging.Filter):
    def filter(self, record):
        record.op_id = _op_id.get()
        return True
