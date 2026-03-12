import hashlib

import gradio as gr
import pandas as pd
from ktem.app import BasePage
from ktem.db.models import User, engine
from ktem.utils import frontend_acl
from sqlmodel import Session, select
from theflow.settings import settings as flowsettings

USERNAME_RULE = """**Benutzernamen-Regeln:**

- Benutzername ist nicht case-sensitiv
- Benutzername muss mindestens 3 Zeichen lang sein
- Benutzername darf höchstens 32 Zeichen lang sein
- Benutzername darf nur Buchstaben, Zahlen und Unterstriche enthalten
"""


PASSWORD_RULE = """**Passwort-Regeln:**

- Passwort muss mindestens 8 Zeichen lang sein
- Passwort muss mindestens einen Großbuchstaben enthalten
- Passwort muss mindestens einen Kleinbuchstaben enthalten
- Passwort muss mindestens eine Zahl enthalten
- Passwort muss mindestens ein Sonderzeichen aus folgender Liste enthalten:
    ^ $ * . [ ] { } ( ) ? - " ! @ # % & / \\ , > < ' : ; | _ ~  + =
"""


def validate_username(usn):
    errors = []
    if len(usn) < 3:
        errors.append("Benutzername muss mindestens 3 Zeichen lang sein")

    if len(usn) > 32:
        errors.append("Benutzername darf höchstens 32 Zeichen lang sein")

    if not usn.replace("_", "").isalnum():
        errors.append(
            "Benutzername darf nur Buchstaben, Zahlen und Unterstriche enthalten"
        )

    return "; ".join(errors)


def validate_password(pwd, pwd_cnf):
    errors = []
    if pwd != pwd_cnf:
        errors.append("Passwörter stimmen nicht überein")

    if len(pwd) < 8:
        errors.append("Passwort muss mindestens 8 Zeichen lang sein")

    if not any(c.isupper() for c in pwd):
        errors.append("Passwort muss mindestens einen Großbuchstaben enthalten")

    if not any(c.islower() for c in pwd):
        errors.append("Passwort muss mindestens einen Kleinbuchstaben enthalten")

    if not any(c.isdigit() for c in pwd):
        errors.append("Passwort muss mindestens eine Zahl enthalten")

    special_chars = "^$*.[]{}()?-\"!@#%&/\\,><':;|_~+="
    if not any(c in special_chars for c in pwd):
        errors.append(
            "Passwort muss mindestens ein Sonderzeichen aus folgender Liste enthalten: "
            f"{special_chars}"
        )

    if errors:
        return "; ".join(errors)

    return ""


def create_user(usn, pwd, user_id=None, is_admin=True) -> bool:
    with Session(engine) as session:
        statement = select(User).where(User.username_lower == usn.lower())
        result = session.exec(statement).all()
        if result:
            print(f'User "{usn}" already exists')
            return False

        hashed_password = hashlib.sha256(pwd.encode()).hexdigest()
        user = User(
            id=user_id,
            username=usn,
            username_lower=usn.lower(),
            password=hashed_password,
            admin=is_admin,
        )
        session.add(user)
        session.commit()
        return True


class UserManagement(BasePage):
    public_events = ["onFrontendAclChanged"]

    def __init__(self, app):
        self._app = app

        self.on_building_ui()
        if hasattr(flowsettings, "KH_FEATURE_USER_MANAGEMENT_ADMIN") and hasattr(
            flowsettings, "KH_FEATURE_USER_MANAGEMENT_PASSWORD"
        ):
            usn = flowsettings.KH_FEATURE_USER_MANAGEMENT_ADMIN
            pwd = flowsettings.KH_FEATURE_USER_MANAGEMENT_PASSWORD

            is_created = create_user(usn, pwd)
            if is_created:
                gr.Info(f'Benutzer "{usn}" wurde erfolgreich erstellt')

    def on_building_ui(self):
        with gr.Tab("Benutzerliste"):
            self.state_user_list = gr.State(value=None)
            self.user_list = gr.DataFrame(
                headers=["id", "username", "admin", "groups"],
                column_widths=[0, 40, 10, 50],
                interactive=False,
            )

            with gr.Group(visible=False) as self._selected_panel:
                self.selected_user_id = gr.State(value=-1)
                self.usn_edit = gr.Textbox(label="Benutzername")
                with gr.Row():
                    self.pwd_edit = gr.Textbox(label="Passwort ändern", type="password")
                    self.pwd_cnf_edit = gr.Textbox(
                        label="Passwortänderung bestätigen",
                        type="password",
                    )
                self.admin_edit = gr.Checkbox(label="Administrator")
                self.user_groups_edit = gr.CheckboxGroup(
                    label="Gruppen",
                    choices=[],
                    value=[],
                )

            with gr.Row(visible=False) as self._selected_panel_btn:
                with gr.Column():
                    self.btn_edit_save = gr.Button("Speichern")
                with gr.Column():
                    self.btn_delete = gr.Button("Löschen")
                    with gr.Row():
                        self.btn_delete_yes = gr.Button(
                            "Löschen bestätigen", variant="primary", visible=False
                        )
                        self.btn_delete_no = gr.Button("Abbrechen", visible=False)
                with gr.Column():
                    self.btn_close = gr.Button("Schließen")

        with gr.Tab("Benutzer erstellen"):
            self.usn_new = gr.Textbox(label="Benutzername", interactive=True)
            self.pwd_new = gr.Textbox(
                label="Passwort", type="password", interactive=True
            )
            self.pwd_cnf_new = gr.Textbox(
                label="Passwort bestätigen", type="password", interactive=True
            )
            with gr.Row():
                gr.Markdown(USERNAME_RULE)
                gr.Markdown(PASSWORD_RULE)
            self.btn_new = gr.Button("Benutzer erstellen")

        with gr.Tab("Gruppenverwaltung"):
            self.state_group_list = gr.State(value=None)
            self.group_list = gr.DataFrame(
                headers=["id", "name", "members"],
                column_widths=[0, 30, 70],
                interactive=False,
            )

            with gr.Row():
                self.group_add_button = gr.Button("Gruppe erstellen", variant="primary")
                self.group_close_button = gr.Button("Schließen", visible=False)
                self.group_delete_button = gr.Button(
                    "Gruppe löschen", variant="stop", visible=False
                )

            with gr.Group(visible=False) as self.group_editor_panel:
                self.selected_group_id = gr.State(value=None)
                self.group_name_edit = gr.Textbox(label="Gruppenname")
                self.group_members_edit = gr.CheckboxGroup(
                    label="Mitglieder",
                    choices=[],
                    value=[],
                )
                self.group_save_button = gr.Button("Gruppe speichern")

    def on_register_events(self):
        self.btn_new.click(
            self.create_user,
            inputs=[self.usn_new, self.pwd_new, self.pwd_cnf_new],
            outputs=[self.usn_new, self.pwd_new, self.pwd_cnf_new],
        ).then(
            self.list_users,
            inputs=self._app.user_id,
            outputs=[self.state_user_list, self.user_list],
        ).then(
            self.list_groups,
            inputs=self._app.user_id,
            outputs=[self.state_group_list, self.group_list],
        )

        self.user_list.select(
            self.select_user,
            inputs=self.user_list,
            outputs=[self.selected_user_id],
            show_progress="hidden",
        )
        self.selected_user_id.change(
            self.on_selected_user_change,
            inputs=[self.selected_user_id],
            outputs=[
                self._selected_panel,
                self._selected_panel_btn,
                self.btn_delete,
                self.btn_delete_yes,
                self.btn_delete_no,
                self.usn_edit,
                self.pwd_edit,
                self.pwd_cnf_edit,
                self.admin_edit,
                self.user_groups_edit,
            ],
            show_progress="hidden",
        )

        self.btn_delete.click(
            self.on_btn_delete_click,
            inputs=[self.selected_user_id],
            outputs=[self.btn_delete, self.btn_delete_yes, self.btn_delete_no],
            show_progress="hidden",
        )
        self.btn_delete_yes.click(
            self.delete_user,
            inputs=[self._app.user_id, self.selected_user_id],
            outputs=[self.selected_user_id],
            show_progress="hidden",
        ).then(
            self.list_users,
            inputs=self._app.user_id,
            outputs=[self.state_user_list, self.user_list],
        ).then(
            self.list_groups,
            inputs=self._app.user_id,
            outputs=[self.state_group_list, self.group_list],
        )

        self.btn_delete_no.click(
            lambda: (
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
            ),
            inputs=[],
            outputs=[self.btn_delete, self.btn_delete_yes, self.btn_delete_no],
            show_progress="hidden",
        )

        on_user_saved = self.btn_edit_save.click(
            self.save_user,
            inputs=[
                self.selected_user_id,
                self.usn_edit,
                self.pwd_edit,
                self.pwd_cnf_edit,
                self.admin_edit,
                self.user_groups_edit,
            ],
            outputs=[self.pwd_edit, self.pwd_cnf_edit],
            show_progress="hidden",
        ).then(
            self.list_users,
            inputs=self._app.user_id,
            outputs=[self.state_user_list, self.user_list],
        ).then(
            self.list_groups,
            inputs=self._app.user_id,
            outputs=[self.state_group_list, self.group_list],
        )

        self.btn_close.click(lambda: -1, outputs=[self.selected_user_id])

        self.group_list.select(
            self.select_group,
            inputs=self.group_list,
            outputs=[self.selected_group_id],
            show_progress="hidden",
        )
        self.selected_group_id.change(
            self.on_selected_group_change,
            inputs=[self.selected_group_id],
            outputs=[
                self.group_editor_panel,
                self.group_add_button,
                self.group_close_button,
                self.group_delete_button,
                self.group_name_edit,
                self.group_members_edit,
            ],
            show_progress="hidden",
        )
        self.group_add_button.click(
            self.start_new_group,
            outputs=[
                self.selected_group_id,
                self.group_editor_panel,
                self.group_add_button,
                self.group_close_button,
                self.group_delete_button,
                self.group_name_edit,
                self.group_members_edit,
            ],
        )
        on_group_saved = self.group_save_button.click(
            self.save_group,
            inputs=[
                self.selected_group_id,
                self.group_name_edit,
                self.group_members_edit,
            ],
            outputs=[self.selected_group_id],
            show_progress="hidden",
        ).then(
            self.list_groups,
            inputs=self._app.user_id,
            outputs=[self.state_group_list, self.group_list],
        ).then(
            self.list_users,
            inputs=self._app.user_id,
            outputs=[self.state_user_list, self.user_list],
        )
        on_group_deleted = self.group_delete_button.click(
            self.delete_group,
            inputs=[self.selected_group_id],
            outputs=[self.selected_group_id],
            show_progress="hidden",
        ).then(
            self.list_groups,
            inputs=self._app.user_id,
            outputs=[self.state_group_list, self.group_list],
        ).then(
            self.list_users,
            inputs=self._app.user_id,
            outputs=[self.state_user_list, self.user_list],
        )
        self.group_close_button.click(lambda: None, outputs=[self.selected_group_id])

        for event in self._app.get_event("onFrontendAclChanged"):
            on_user_saved = on_user_saved.then(**event)
            on_group_saved = on_group_saved.then(**event)
            on_group_deleted = on_group_deleted.then(**event)

    def on_subscribe_public_events(self):
        self._app.subscribe_event(
            name="onSignIn",
            definition={
                "fn": self.list_users,
                "inputs": [self._app.user_id],
                "outputs": [self.state_user_list, self.user_list],
            },
        )
        self._app.subscribe_event(
            name="onSignIn",
            definition={
                "fn": self.list_groups,
                "inputs": [self._app.user_id],
                "outputs": [self.state_group_list, self.group_list],
            },
        )
        self._app.subscribe_event(
            name="onSignOut",
            definition={
                "fn": lambda: ("", "", "", None, None, -1, None, None),
                "outputs": [
                    self.usn_new,
                    self.pwd_new,
                    self.pwd_cnf_new,
                    self.state_user_list,
                    self.user_list,
                    self.selected_user_id,
                    self.state_group_list,
                    self.group_list,
                ],
            },
        )
        self._app.subscribe_event(
            name="onFrontendAclChanged",
            definition={
                "fn": self.list_users,
                "inputs": [self._app.user_id],
                "outputs": [self.state_user_list, self.user_list],
                "show_progress": "hidden",
            },
        )
        self._app.subscribe_event(
            name="onFrontendAclChanged",
            definition={
                "fn": self.list_groups,
                "inputs": [self._app.user_id],
                "outputs": [self.state_group_list, self.group_list],
                "show_progress": "hidden",
            },
        )

    def _get_all_users(self) -> list[User]:
        with Session(engine) as session:
            return list(session.exec(select(User)).all())

    def _get_group_choices(self):
        return frontend_acl.get_group_choices()

    def _get_user_choices(self):
        return [(user.username, user.id) for user in self._get_all_users()]

    def create_user(self, usn, pwd, pwd_cnf):
        errors = validate_username(usn)
        if errors:
            gr.Warning(errors)
            return usn, pwd, pwd_cnf

        errors = validate_password(pwd, pwd_cnf)
        if errors:
            gr.Warning(errors)
            return usn, pwd, pwd_cnf

        with Session(engine) as session:
            statement = select(User).where(User.username_lower == usn.lower())
            result = session.exec(statement).all()
            if result:
                gr.Warning(f'Benutzername "{usn}" existiert bereits')
                return usn, pwd, pwd_cnf

            hashed_password = hashlib.sha256(pwd.encode()).hexdigest()
            user = User(
                username=usn, username_lower=usn.lower(), password=hashed_password
            )
            session.add(user)
            session.commit()
            gr.Info(f'Benutzer "{usn}" wurde erfolgreich erstellt')

        return "", "", ""

    def list_users(self, user_id):
        if user_id is None:
            return [], pd.DataFrame.from_records(
                [{"id": "-", "username": "-", "admin": "-", "groups": "-"}]
            )

        with Session(engine) as session:
            statement = select(User).where(User.id == user_id)
            user = session.exec(statement).one()
            if not user.admin:
                return [], pd.DataFrame.from_records(
                    [{"id": "-", "username": "-", "admin": "-", "groups": "-"}]
                )

            users = session.exec(select(User)).all()
            results = []
            for item in users:
                groups = frontend_acl.get_user_group_names(item.id)
                results.append(
                    {
                        "id": item.id,
                        "username": item.username,
                        "admin": item.admin,
                        "groups": ", ".join(groups) if groups else "-",
                    }
                )

        if results:
            user_list = pd.DataFrame.from_records(results)
        else:
            user_list = pd.DataFrame.from_records(
                [{"id": "-", "username": "-", "admin": "-", "groups": "-"}]
            )

        return results, user_list

    def list_groups(self, user_id):
        if user_id is None:
            return [], pd.DataFrame.from_records(
                [{"id": "-", "name": "-", "members": "-"}]
            )

        with Session(engine) as session:
            current_user = session.exec(select(User).where(User.id == user_id)).first()
            if not current_user or not current_user.admin:
                return [], pd.DataFrame.from_records(
                    [{"id": "-", "name": "-", "members": "-"}]
                )

            user_name_by_id = {
                user.id: user.username for user in session.exec(select(User)).all()
            }

        results = []
        for group in frontend_acl.list_groups():
            member_names = [
                user_name_by_id.get(member_id, member_id) for member_id in group["members"]
            ]
            results.append(
                {
                    "id": group["id"],
                    "name": group["name"],
                    "members": ", ".join(member_names) if member_names else "-",
                }
            )

        if results:
            group_list = pd.DataFrame.from_records(results)
        else:
            group_list = pd.DataFrame.from_records(
                [{"id": "-", "name": "-", "members": "-"}]
            )

        return results, group_list

    def select_user(self, user_list, ev: gr.SelectData):
        if ev.value == "-" and ev.index[0] == 0:
            gr.Info("Es ist kein Benutzer geladen. Bitte aktualisiere die Benutzerliste")
            return -1

        if not ev.selected:
            return -1

        return user_list["id"][ev.index[0]]

    def on_selected_user_change(self, selected_user_id):
        group_choices = self._get_group_choices()
        if selected_user_id == -1:
            return (
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=""),
                gr.update(value=False),
                gr.update(choices=group_choices, value=[]),
            )

        with Session(engine) as session:
            statement = select(User).where(User.id == selected_user_id)
            user = session.exec(statement).one()

        return (
            gr.update(visible=True),
            gr.update(visible=True),
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(value=user.username),
            gr.update(value=""),
            gr.update(value=""),
            gr.update(value=user.admin),
            gr.update(
                choices=group_choices,
                value=frontend_acl.get_user_group_ids(selected_user_id),
            ),
        )

    def on_btn_delete_click(self, selected_user_id):
        if selected_user_id is None:
            gr.Warning("Kein Benutzer ausgewählt")
            return (
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
            )

        return (
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(visible=True),
        )

    def save_user(self, selected_user_id, usn, pwd, pwd_cnf, admin, group_ids):
        errors = validate_username(usn)
        if errors:
            gr.Warning(errors)
            return pwd, pwd_cnf

        if pwd:
            errors = validate_password(pwd, pwd_cnf)
            if errors:
                gr.Warning(errors)
                return pwd, pwd_cnf

        with Session(engine) as session:
            statement = select(User).where(
                User.username_lower == usn.lower(),
                User.id != selected_user_id,
            )
            existing = session.exec(statement).first()
            if existing:
                gr.Warning(
                    f'Benutzername "{usn}" existiert bereits. Bitte verwende einen eindeutigen Namen.'
                )
                return pwd, pwd_cnf

            statement = select(User).where(User.id == selected_user_id)
            user = session.exec(statement).one()
            user.username = usn
            user.username_lower = usn.lower()
            user.admin = admin
            if pwd:
                user.password = hashlib.sha256(pwd.encode()).hexdigest()
            session.commit()

        frontend_acl.set_user_groups(selected_user_id, group_ids or [])
        gr.Info(f'Benutzer "{usn}" wurde erfolgreich aktualisiert')
        return "", ""

    def delete_user(self, current_user, selected_user_id):
        if current_user == selected_user_id:
            gr.Warning("Du kannst dich nicht selbst löschen")
            return selected_user_id

        frontend_acl.set_user_groups(selected_user_id, [])
        with Session(engine) as session:
            statement = select(User).where(User.id == selected_user_id)
            user = session.exec(statement).one()
            session.delete(user)
            session.commit()
            gr.Info(f'Benutzer "{user.username}" wurde erfolgreich gelöscht')
        return -1

    def select_group(self, group_list, ev: gr.SelectData):
        if ev.value == "-" and ev.index[0] == 0:
            gr.Info("Es ist keine Gruppe geladen")
            return None

        if not ev.selected:
            return None

        return group_list["id"][ev.index[0]]

    def start_new_group(self):
        return (
            "new",
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(value=""),
            gr.update(choices=self._get_user_choices(), value=[]),
        )

    def on_selected_group_change(self, selected_group_id):
        user_choices = self._get_user_choices()
        if selected_group_id == "new":
            return (
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(value=""),
                gr.update(choices=user_choices, value=[]),
            )

        if not selected_group_id:
            return (
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(value=""),
                gr.update(choices=user_choices, value=[]),
            )

        group = frontend_acl.get_group(selected_group_id)
        if group is None:
            return (
                gr.update(visible=False),
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(value=""),
                gr.update(choices=user_choices, value=[]),
            )

        return (
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=True),
            gr.update(visible=True),
            gr.update(value=group["name"]),
            gr.update(choices=user_choices, value=group["members"]),
        )

    def save_group(self, group_id, group_name, member_ids):
        try:
            if group_id and group_id != "new":
                group = frontend_acl.update_group(group_id, group_name, member_ids or [])
            else:
                group = frontend_acl.create_group(group_name, member_ids or [])
        except ValueError as exc:
            gr.Warning(str(exc))
            return group_id

        gr.Info(f'Gruppe "{group["name"]}" wurde gespeichert')
        return group["id"]

    def delete_group(self, group_id):
        if not group_id:
            gr.Warning("Keine Gruppe ausgewählt")
            return group_id

        group = frontend_acl.get_group(group_id)
        if group is None:
            gr.Warning("Gruppe wurde nicht gefunden")
            return None

        frontend_acl.delete_group(group_id)
        gr.Info(f'Gruppe "{group["name"]}" wurde gelöscht')
        return None
