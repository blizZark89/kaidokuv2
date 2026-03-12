from textwrap import dedent

import gradio as gr
from ktem.app import BasePage


class HintPage(BasePage):
    def __init__(self, app):
        self._app = app
        self.on_building_ui()

    def on_building_ui(self):
        with gr.Accordion(label="Hinweis", open=False):
            gr.Markdown(
                dedent(
                    """
                - Du kannst Text aus der Chat-Antwort markieren, um **passende Quellenstellen** im rechten Bereich hervorzuheben.
                - **Quellenangaben** lassen sich sowohl im PDF-Viewer als auch im Rohtext ansehen.
                - Im Menü **Chat-Einstellungen** kannst du das Zitierformat und erweitertes (CoT-)Denken anpassen.
                - Du willst **mehr ausprobieren**? Im Bereich **Hilfe** erfährst du, wie du deinen privaten Bereich erstellst.
            """  # noqa
                )
            )
