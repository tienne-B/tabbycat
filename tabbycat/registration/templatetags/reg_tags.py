from django import template

register = template.Library()


@register.filter
def currency(value):
    return format(value/100, '.2f')
