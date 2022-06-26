import uuid
from datetime import datetime


def iso_validation(dt_str: str) -> datetime or None:
    try:
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    except:
        return None
    return dt


def uuid_validation(value: str) -> bool:
    try:
        uuid.UUID(value)
    except:
        return False
    return True


def type_validation(new_type: str, price: int) -> bool:
    # valid typing check
    if new_type not in ['OFFER', 'CATEGORY']:
        return False

    # price check
    is_category = ('CATEGORY' == new_type)
    if price is not None and is_category:
        return False
    elif ((type(price) is not int) or price < 0) and not is_category:
        return False

    return True


def two_types_validation(new_type: str, old_is_category: bool, price: int) -> bool:
    return ('CATEGORY' == new_type) == old_is_category and type_validation(new_type, price)


def import_req_validation(data: dict) -> bool:
    if set(data) != {'items', 'updateDate'}:
        return False
    if type(data['items']) is list and type(data['updateDate']) is str:
        return True
    return False


def unit_fields_validation(unit: dict) -> bool:
    # keys validation
    required_keys = {'id', 'name', 'type'}
    all_keys = required_keys | {'parentId', 'price'}
    if not (required_keys <= (keys := set(unit)) <= all_keys):
        return False
    else:
        for missing_key in (all_keys - keys):
            unit[missing_key] = None

    # value validation
    if type(unit['name']) is not str:
        return False
    if (not uuid_validation(unit['id'])) or (unit['parentId'] is not None and not uuid_validation(unit['parentId'])) \
            or (unit['id'] == unit['parentId']):
        return False
    if not type_validation(unit['type'], unit['price']):
        return False

    return True
