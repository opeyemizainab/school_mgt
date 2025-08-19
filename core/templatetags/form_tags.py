from django import template

register = template.Library()

@register.filter(name='add_class')
def add_class(field, css):
    """
    Adds a CSS class to a form field widget.
    Usage: {{ form.field_name|add_class:"form-control" }}
    """
    return field.as_widget(attrs={"class": css})
