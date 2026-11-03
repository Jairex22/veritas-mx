from django import template

register = template.Library()


@register.filter
def dictkey(d, key):
    try:
        return d.get(key, "")
    except AttributeError:
        return ""


@register.filter
def split(value, sep=" "):
    return str(value).split(sep)
