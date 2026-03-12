import json
import uuid
from pathlib import Path

from theflow.settings import settings as flowsettings

ACL_STORAGE_PATH = Path(flowsettings.KH_APP_DATA_DIR) / "frontend_acl.json"


def _default_store() -> dict:
    return {
        "groups": [],
        "document_shares": {},
    }


def _normalize_group(group: dict) -> dict:
    return {
        "id": group.get("id", uuid.uuid4().hex),
        "name": group.get("name", "").strip(),
        "members": sorted(set(group.get("members", []))),
    }


def _normalize_store(store: dict | None) -> dict:
    if not isinstance(store, dict):
        store = {}

    groups = [
        _normalize_group(group)
        for group in store.get("groups", [])
        if group.get("name", "").strip()
    ]
    known_group_ids = {group["id"] for group in groups}

    document_shares = {}
    for index_id, shares in store.get("document_shares", {}).items():
        if not isinstance(shares, dict):
            continue
        normalized_index_shares = {}
        for document_id, item in shares.items():
            if not isinstance(item, dict):
                continue
            group_ids = sorted(
                {group_id for group_id in item.get("group_ids", []) if group_id in known_group_ids}
            )
            normalized_index_shares[document_id] = {
                "owner_id": item.get("owner_id", ""),
                "group_ids": group_ids,
            }
        document_shares[str(index_id)] = normalized_index_shares

    return {
        "groups": sorted(groups, key=lambda item: item["name"].lower()),
        "document_shares": document_shares,
    }


def load_store() -> dict:
    if not ACL_STORAGE_PATH.exists():
        return _default_store()

    try:
        with ACL_STORAGE_PATH.open() as file:
            return _normalize_store(json.load(file))
    except (OSError, json.JSONDecodeError):
        return _default_store()


def save_store(store: dict) -> dict:
    normalized = _normalize_store(store)
    ACL_STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ACL_STORAGE_PATH.open("w") as file:
        json.dump(normalized, file, indent=2, sort_keys=True)
    return normalized


def list_groups() -> list[dict]:
    return load_store()["groups"]


def get_group(group_id: str) -> dict | None:
    for group in list_groups():
        if group["id"] == group_id:
            return group
    return None


def get_group_choices() -> list[tuple[str, str]]:
    return [(group["name"], group["id"]) for group in list_groups()]


def get_user_group_ids(user_id: str | None) -> list[str]:
    if not user_id:
        return []
    return [group["id"] for group in list_groups() if user_id in group["members"]]


def get_user_group_names(user_id: str | None) -> list[str]:
    if not user_id:
        return []
    return [group["name"] for group in list_groups() if user_id in group["members"]]


def create_group(name: str, member_ids: list[str] | None = None) -> dict:
    store = load_store()
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Gruppenname darf nicht leer sein")

    for group in store["groups"]:
        if group["name"].lower() == normalized_name.lower():
            raise ValueError(f'Gruppe "{normalized_name}" existiert bereits')

    group = {
        "id": uuid.uuid4().hex,
        "name": normalized_name,
        "members": sorted(set(member_ids or [])),
    }
    store["groups"].append(group)
    save_store(store)
    return group


def update_group(group_id: str, name: str, member_ids: list[str] | None = None) -> dict:
    store = load_store()
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Gruppenname darf nicht leer sein")

    group_to_update = None
    for group in store["groups"]:
        if group["id"] == group_id:
            group_to_update = group
        elif group["name"].lower() == normalized_name.lower():
            raise ValueError(f'Gruppe "{normalized_name}" existiert bereits')

    if group_to_update is None:
        raise ValueError("Gruppe wurde nicht gefunden")

    group_to_update["name"] = normalized_name
    group_to_update["members"] = sorted(set(member_ids or []))
    save_store(store)
    return group_to_update


def delete_group(group_id: str) -> None:
    store = load_store()
    store["groups"] = [group for group in store["groups"] if group["id"] != group_id]

    for shares in store["document_shares"].values():
        for item in shares.values():
            item["group_ids"] = [gid for gid in item.get("group_ids", []) if gid != group_id]

    save_store(store)


def set_user_groups(user_id: str, group_ids: list[str]) -> None:
    store = load_store()
    selected_group_ids = set(group_ids)
    for group in store["groups"]:
        members = set(group.get("members", []))
        if group["id"] in selected_group_ids:
            members.add(user_id)
        else:
            members.discard(user_id)
        group["members"] = sorted(members)
    save_store(store)


def get_document_share(index_id: int | str, document_id: str, owner_id: str = "") -> dict:
    store = load_store()
    index_key = str(index_id)
    item = store["document_shares"].get(index_key, {}).get(document_id)
    if item:
        return {
            "owner_id": item.get("owner_id", owner_id),
            "group_ids": list(item.get("group_ids", [])),
        }
    return {
        "owner_id": owner_id,
        "group_ids": [],
    }


def set_document_share(
    index_id: int | str,
    document_id: str,
    owner_id: str,
    group_ids: list[str] | None = None,
) -> dict:
    store = load_store()
    index_key = str(index_id)
    store["document_shares"].setdefault(index_key, {})
    store["document_shares"][index_key][document_id] = {
        "owner_id": owner_id,
        "group_ids": sorted(set(group_ids or [])),
    }
    save_store(store)
    return store["document_shares"][index_key][document_id]


def can_user_view_document(
    index_id: int | str,
    current_user_id: str | None,
    owner_id: str | None,
    document_id: str,
    is_public_document: bool = False,
) -> bool:
    if not current_user_id:
        return False

    if owner_id == current_user_id:
        return True

    if is_public_document and not owner_id:
        return True

    share = get_document_share(index_id=index_id, document_id=document_id, owner_id=owner_id or "")
    if not share["group_ids"]:
        return False

    return bool(set(get_user_group_ids(current_user_id)).intersection(share["group_ids"]))


def get_document_group_names(index_id: int | str, document_id: str) -> list[str]:
    share = get_document_share(index_id=index_id, document_id=document_id)
    group_name_by_id = {group["id"]: group["name"] for group in list_groups()}
    return [group_name_by_id[group_id] for group_id in share["group_ids"] if group_id in group_name_by_id]
