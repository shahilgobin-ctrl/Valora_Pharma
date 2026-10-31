from django import template
register = template.Library()


@register.simple_tag(takes_context=True)
def page_query(context, number):
    params = context["request"].GET.copy()
    params["page"] = number
    return "?" + params.urlencode()


@register.simple_tag(takes_context=True)
def report_query(context, kind):
    params = context["request"].GET.copy()
    params["type"] = kind
    params.pop("page", None)
    params.pop("format", None)
    return "?" + params.urlencode()


@register.filter
def medicine_strength(value):
    return (value or "").rsplit(" - ", 1)[0]
