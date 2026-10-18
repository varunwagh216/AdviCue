"""Backend-owned numeric substitutions for local-model generated prose."""
from __future__ import annotations
import re

class UnverifiedNumericClaim(ValueError):
    pass


def render_fact_template(prose:str, allowed:dict)->str:
    """Render approved keys only; reject ANY independent digits/currencies.

    Only the back end computes numerics. A LLM must never manufacture a number
    in either a brief summary or a proposed review question.
    """
    keys=re.findall(r'\[\[([^\]]+)\]\]',prose)
    if '[[' in re.sub(r'\[\[[^\]]+\]\]','',prose):
        raise UnverifiedNumericClaim('Malformed numerical placeholder')
    for key in keys:
        if key not in allowed or allowed[key] is None:
            raise UnverifiedNumericClaim('Unknown or unavailable numerical placeholder')
    remaining=re.sub(r'\[\[[^\]]+\]\]','',prose)
    if re.search(r'[0-9₹$]',remaining):
        raise UnverifiedNumericClaim('Unsourced numeric or currency claim')
    for key in set(keys):prose=prose.replace(f'[[{key}]]',str(allowed[key]))
    return prose
