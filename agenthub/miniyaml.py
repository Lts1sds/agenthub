def loads(text):
    lines = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(raw.rstrip())
    if not lines:
        return {}
    value, _ = _parse_block(lines, 0, _indent_of(lines[0]))
    return value if isinstance(value, (dict, list)) else {}


def _indent_of(line):
    return len(line) - len(line.lstrip())


def _parse_scalar(s):
    s = s.strip()
    if not s or s.startswith("#"):
        return None
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    if s in ("null", "~"):
        return None
    for cast in (int, float):
        try:
            return cast(s)
        except ValueError:
            pass
    return s


def _parse_block(lines, i, indent):
    if lines[i].lstrip().startswith("- "):
        return _parse_list(lines, i, indent)
    return _parse_dict(lines, i, indent)


def _parse_list(lines, i, indent):
    items = []
    while i < len(lines):
        line = lines[i]
        cur = _indent_of(line)
        if cur < indent:
            break
        if cur > indent:
            raise ValueError("unexpected indent at line %d: %r" % (i + 1, line))
        stripped = line.strip()
        if not stripped.startswith("- "):
            break
        items.append(_parse_scalar(stripped[2:]))
        i += 1
    return items, i


def _parse_dict(lines, i, indent):
    result = {}
    while i < len(lines):
        line = lines[i]
        cur = _indent_of(line)
        if cur < indent:
            break
        if cur > indent:
            raise ValueError("unexpected indent at line %d: %r" % (i + 1, line))
        stripped = line.strip()
        if stripped.startswith("- "):
            break
        if ":" not in stripped:
            raise ValueError("expected 'key: value' at line %d: %r" % (i + 1, line))
        key, _, rest = stripped.partition(":")
        key = key.strip()
        rest = rest.strip()
        i += 1
        if rest:
            result[key] = _parse_scalar(rest)
        else:
            if i < len(lines) and _indent_of(lines[i]) > indent:
                value, i = _parse_block(lines, i, _indent_of(lines[i]))
                result[key] = value
            else:
                result[key] = None
    return result, i
