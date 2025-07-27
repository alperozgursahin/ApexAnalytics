from django import template

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Bir sözlükten (dictionary) belirtilen anahtar (key) ile değeri döndürür.
    Template içinde: {{ my_dictionary|get_item:my_key }}
    """
    return dictionary.get(key)