from django.db.models import Func


class RegexReplace(Func):
    function = 'REGEXP_REPLACE'
