"""Urwid TUI for the PyTemplate template downloader."""

import threading
from typing import Dict, List, Optional, Callable, Any

import urwid
import queue

from .downloadtemplate import (
    TemplateDownloadError,
    download_template,
    fetch_registry,
)


class TemplateDownloaderTUI:
    """Urwid downloader view that runs inside an existing MainLoop."""

    palette = [
        ("header", "light cyan", "dark blue"),
        ("body", "white", "black"),
        ("selected", "black", "light cyan"),
        ("footer", "light gray", "dark blue"),
        ("title", "light cyan", "black", "bold"),
        ("success", "light green", "black"),
        ("error", "light red", "black"),
        ("warning", "yellow", "black"),
        ("info", "light cyan", "black"),
        ("dim", "dark gray", "black"),
    ]

    def __init__(
            self,
            manager,
            main_loop: urwid.MainLoop,
            on_close: Optional[Callable[[], None]] = None,
    ):
        self.manager = manager
        self.main_loop = main_loop
        self.on_close = on_close

        self.templates: List[Dict] = []
        self.selected_index = 0
        self.selected_template: Optional[Dict] = None

        self.current_view = "list"

        self.loading = False
        self.downloading = False

        self.status = ""

        # ----------------------------------------------------------
        # Progress widgets
        # ----------------------------------------------------------

        self.progress = urwid.ProgressBar(
            "body",
            "selected",
            0,
            100,
        )

        self.reference_progress = urwid.ProgressBar(
            "body",
            "selected",
            0,
            100,
        )

        self.progress_text = urwid.Text(
            "",
            align="center",
        )

        self.reference_text = urwid.Text(
            "",
            align="center",
        )

        # ----------------------------------------------------------
        # Main widgets
        # ----------------------------------------------------------

        self.content_walker = urwid.SimpleFocusListWalker([])

        self.header = urwid.AttrMap(
            urwid.Text(
                " PyTemplate Template Downloader ",
                align="center",
            ),
            "header",
        )

        self.status_bar = urwid.AttrMap(
            urwid.Text(
                "",
                align="center",
            ),
            "footer",
        )

        self.content = urwid.ListBox(
            self.content_walker
        )

        self.root = urwid.Pile(
            [
                ("pack", self.header),
                ("pack", urwid.Divider("─")),
                self.content,
                ("pack", urwid.Divider("─")),
                ("pack", self.status_bar),
            ]
        )

        # Keep track of whether an overlay is currently displayed.
        self.dialog_open = False

        self._ui_queue: queue.Queue = queue.Queue()
        self._ui_polling = False
        self._ui_poll_interval = 0.05

    # ==============================================================
    # Urwid compatibility helpers
    # ==============================================================

    @staticmethod
    def _text(
            text: str = "",
            align: str = "left",
            style: Optional[str] = None,
    ) -> urwid.Widget:
        """
        Create styled Text.

        We intentionally do not use Text(attrib=...) because newer
        Urwid versions no longer accept that keyword.
        """
        widget = urwid.Text(
            text,
            align=align,
        )

        if style:
            return urwid.AttrMap(
                widget,
                style,
            )

        return widget

    @staticmethod
    def _center(
            widget: urwid.Widget,
    ) -> urwid.Widget:
        """Center a widget horizontally."""
        return urwid.Padding(
            widget,
            align="center",
            width=("relative", 100),
        )

    def _schedule(
            self,
            callback: Callable,
            *args,
    ) -> None:
        """
        Queue a callback for execution on the Urwid UI thread.

        Worker threads must never directly modify Urwid widgets.
        The main loop periodically drains this queue.
        """
        self._ui_queue.put(
            (
                callback,
                args,
            )
        )

    def _start_ui_poller(self):
        """
        Start the UI callback poller.

        This is intentionally implemented with set_alarm_in()
        instead of watch_pipe(), because Urwid's Windows event loop
        does not provide watch_pipe().
        """
        if self._ui_polling:
            return

        self._ui_polling = True

        self.main_loop.set_alarm_in(
            self._ui_poll_interval,
            self._poll_ui_queue,
        )

    def _poll_ui_queue(
            self,
            loop,
            user_data=None,
    ):
        """
        Execute callbacks queued by worker threads.

        This method always runs on Urwid's main/UI thread.
        """
        try:
            while True:
                try:
                    callback, args = self._ui_queue.get_nowait()
                except queue.Empty:
                    break

                try:
                    callback(*args)
                except Exception:
                    # Never allow one UI callback to kill the
                    # Urwid event loop.
                    import traceback

                    traceback.print_exc()

        finally:
            if self._ui_polling:
                self.main_loop.set_alarm_in(
                    self._ui_poll_interval,
                    self._poll_ui_queue,
                )

    def _process_ui_callbacks(self, data):
        """
        Process callbacks queued by worker threads.

        This method is executed inside Urwid's main event loop.
        """

        with self._ui_callbacks_lock:
            callbacks = self._ui_callbacks[:]
            self._ui_callbacks.clear()

        for callback, args in callbacks:
            try:
                callback(*args)
            except Exception:
                # Do not allow a UI callback exception to kill
                # the Urwid event loop.
                import traceback

                traceback.print_exc()

        self._refresh()

        return True

    # ==============================================================
    # Opening / closing
    # ==============================================================

    def open(self):
        """Open the downloader inside the existing Urwid MainLoop."""
        self.main_loop.widget = self.root

        self.current_view = "list"
        self.selected_index = 0
        self.selected_template = None

        self._start_ui_poller()

        self._show_loading()
        self._refresh_registry()

        self._refresh()

    def close(self):
        """Return control to the template manager."""

        if self.loading or self.downloading:
            return

        self._close_dialog()

        try:
            self.main_loop.remove_watch_pipe(
                self._ui_pipe
            )
        except Exception:
            pass

        if self.on_close:
            self.on_close()

        self._refresh()

    # ==============================================================
    # Main UI
    # ==============================================================

    def _show_loading(self):
        """Show registry loading screen."""

        self.content_walker[:] = [
            urwid.Divider(),

            self._center(
                self._text(
                    "Fetching template registry...",
                    align="center",
                    style="title",
                )
            ),

            urwid.Divider(),

            self._center(
                self._text(
                    "Please wait.",
                    align="center",
                    style="dim",
                )
            ),

            urwid.Divider(),
        ]

        self._set_status(
            "Loading registry..."
        )

        self._refresh()

    def _show_list(self):
        """Display the template list."""

        self.current_view = "list"

        widgets = [
            self._text(
                "Available Templates",
                align="center",
                style="title",
            ),

            urwid.Divider("─"),
        ]

        if not self.templates:
            widgets.append(
                self._text(
                    "No templates found.",
                    align="center",
                    style="warning",
                )
            )

        else:
            for template in self.templates:
                name = template.get(
                    "name",
                    "unknown",
                )

                description = template.get(
                    "description",
                    "No description",
                )

                author = template.get(
                    "author",
                    "Unknown",
                )

                version = template.get(
                    "version",
                    "",
                )

                refs = template.get(
                    "references",
                    [],
                )

                text = name

                if version:
                    text += f"  v{version}"

                if refs:
                    text += f"  [{len(refs)} refs]"

                text += f"\n    {description}"
                text += f"\n    by {author}"

                widget = urwid.AttrMap(
                    urwid.Padding(
                        urwid.Text(text),
                        left=2,
                        right=2,
                    ),
                    "body",
                    "selected",
                )

                widgets.append(widget)

        widgets.extend(
            [
                urwid.Divider(),

                self._text(
                    "↑/↓ Navigate   Enter Details   "
                    "u Manual URL   r Refresh   "
                    "b Back   q Quit",
                    align="center",
                ),

                self._text(
                    "Press Enter to inspect a template.",
                    align="center",
                    style="dim",
                ),
            ]
        )

        self.content_walker[:] = widgets

        self._update_selection()

        self._set_status(
            f"{len(self.templates)} template(s) available"
        )

        self._refresh()

    def _update_selection(self):
        """Update the highlighted template."""

        if not self.templates:
            return

        # First two widgets are:
        #
        #   0 = title
        #   1 = divider
        #
        # Therefore template index N is widget N + 2.
        widget_index = self.selected_index + 2

        for index, widget in enumerate(
                self.content_walker
        ):
            if isinstance(widget, urwid.AttrMap):
                if index == widget_index:
                    widget.set_attr_map(
                        {
                            None: "selected"
                        }
                    )
                else:
                    widget.set_attr_map(
                        {
                            None: "body"
                        }
                    )

        # Move the ListBox focus to the selected template.
        try:
            self.content.set_focus(widget_index)
        except Exception:
            pass

        self._refresh()

    # ==============================================================
    # Detail view
    # ==============================================================

    def _show_detail(
            self,
            template: Dict,
    ):
        """Show template details."""

        self.current_view = "detail"
        self.selected_template = template

        name = template.get(
            "name",
            "Unknown",
        )

        description = template.get(
            "description",
            "No description",
        )

        author = template.get(
            "author",
            "Unknown",
        )

        version = template.get(
            "version",
            "Unknown",
        )

        category = template.get(
            "category",
            "Unknown",
        )

        tags = template.get(
            "tags",
            [],
        )

        references = template.get(
            "references",
            [],
        )

        widgets = [
            self._text(
                f"Template: {name}",
                align="center",
                style="title",
            ),

            urwid.Divider("─"),

            urwid.Text(
                f"Description: {description}"
            ),

            urwid.Text(
                f"Author:      {author}"
            ),

            urwid.Text(
                f"Version:     {version}"
            ),

            urwid.Text(
                f"Category:    {category}"
            ),
        ]

        if tags:
            widgets.append(
                urwid.Text(
                    f"Tags:        {', '.join(tags)}"
                )
            )

        widgets.extend(
            [
                urwid.Divider(),

                urwid.Text(
                    f"References: {len(references)}"
                ),
            ]
        )

        for ref in references[:10]:
            widgets.append(
                urwid.Text(
                    f"  @{ref}"
                )
            )

        if len(references) > 10:
            widgets.append(
                urwid.Text(
                    f"  ... and "
                    f"{len(references) - 10} more"
                )
            )

        widgets.extend(
            [
                urwid.Divider(),

                self._text(
                    "Actions",
                    align="center",
                    style="title",
                ),

                urwid.Divider("─"),

                self._text(
                    "[Enter] Download template",
                    align="center",
                ),

                self._text(
                    "[b] Back",
                    align="center",
                ),

                self._text(
                    "[q] Quit",
                    align="center",
                ),
            ]
        )

        self.content_walker[:] = widgets

        self._set_status(
            f"Viewing: {name}"
        )

        self._refresh()

    # ==============================================================
    # Progress view
    # ==============================================================

    def _show_download_view(
            self,
            template: Dict,
    ):
        """Show download progress."""

        self.current_view = "download"

        name = template.get(
            "name",
            "Unknown",
        )

        self.progress = urwid.ProgressBar(
            "body",
            "selected",
            0,
            100,
        )

        self.reference_progress = urwid.ProgressBar(
            "body",
            "selected",
            0,
            100,
        )

        self.progress_text = urwid.Text(
            "Preparing download...",
            align="center",
        )

        self.reference_text = urwid.Text(
            "",
            align="center",
        )

        self.content_walker[:] = [
            self._text(
                f"Downloading: {name}",
                align="center",
                style="title",
            ),

            urwid.Divider("─"),

            self._text(
                "Template",
                align="center",
            ),

            self.progress,

            self.progress_text,

            urwid.Divider(),

            self._text(
                "References",
                align="center",
            ),

            self.reference_progress,

            self.reference_text,

            urwid.Divider(),

            self._text(
                "Please wait...",
                align="center",
                style="dim",
            ),
        ]

        self._set_status(
            f"Downloading {name}..."
        )

        self._refresh()

    def _update_main_progress(
            self,
            downloaded: int,
            total: int,
    ):
        """Update main template progress."""

        if total > 0:
            percentage = min(
                int(downloaded * 100 / total),
                100,
            )
        else:
            percentage = 0

        self.progress.set_completion(
            percentage
        )

        if total:
            self.progress_text.set_text(
                f"{self._format_size(downloaded)} / "
                f"{self._format_size(total)} "
                f"({percentage}%)"
            )
        else:
            self.progress_text.set_text(
                f"{self._format_size(downloaded)} downloaded"
            )

        self._refresh()

    def _update_reference_progress(
            self,
            ref_name: str,
            downloaded: int,
            total: int,
    ):
        """Update reference-file progress."""

        if total > 0:
            percentage = min(
                int(downloaded * 100 / total),
                100,
            )
        else:
            percentage = 0

        self.reference_progress.set_completion(
            percentage
        )

        if total:
            self.reference_text.set_text(
                f"@{ref_name}  "
                f"{self._format_size(downloaded)} / "
                f"{self._format_size(total)} "
                f"({percentage}%)"
            )
        else:
            self.reference_text.set_text(
                f"@{ref_name}  "
                f"{self._format_size(downloaded)}"
            )

        self._refresh()

    # ==============================================================
    # Downloading
    # ==============================================================

    def _download_selected(self):
        """Download the selected template."""

        if not self.selected_template:
            return

        template = self.selected_template

        self._show_download_view(
            template
        )

        self.downloading = True

        thread = threading.Thread(
            target=self._download_worker,
            args=(template,),
            daemon=True,
        )

        thread.start()

    def _download_worker(
            self,
            template: Dict,
    ):
        """Download in a background thread."""
        try:
            result = download_template(
                template,
                progress_callback=self._threadsafe_main_progress,
                reference_progress_callback=self._threadsafe_reference_progress,
                overwrite=False,
            )

            self._schedule(
                self._download_finished,
                result,
            )

        except FileExistsError:
            self._schedule(
                self._ask_overwrite,
                template,
            )

        except TemplateDownloadError as e:
            self._schedule(
                self._download_failed,
                str(e),
            )

        except Exception as e:
            self._schedule(
                self._download_failed,
                f"Unexpected error: {e}",
            )

    def _threadsafe_main_progress(
            self,
            downloaded: int,
            total: int,
    ):
        self._schedule(
            self._update_main_progress,
            downloaded,
            total,
        )

    def _threadsafe_reference_progress(
            self,
            ref_name: str,
            downloaded: int,
            total: int,
    ):
        self._schedule(
            self._update_reference_progress,
            ref_name,
            downloaded,
            total,
        )

    def _download_finished(
            self,
            result: Dict,
    ):
        """Handle successful download."""

        self.downloading = False

        name = result.get(
            "name",
            "template",
        )

        downloaded = result.get(
            "references_downloaded",
            0,
        )

        total = result.get(
            "references_total",
            0,
        )

        self._show_message(
            "Download Complete",
            [
                f"Successfully downloaded '{name}'.",
                "",
                f"References: {downloaded}/{total}",
            ],
            [
                (
                    "OK",
                    self._return_to_list,
                ),
            ],
        )

    def _download_failed(
            self,
            message: str,
    ):
        """Handle failed download."""

        self.downloading = False

        self._show_message(
            "Download Failed",
            [message],
            [
                (
                    "OK",
                    self._return_to_list,
                ),
            ],
            error=True,
        )

    # ==============================================================
    # Overwrite
    # ==============================================================

    def _ask_overwrite(
            self,
            template: Dict,
    ):
        """Ask whether an existing template should be overwritten."""

        self.downloading = False

        name = template.get(
            "name",
            "template",
        )

        self._show_message(
            "Template Already Exists",
            [
                f"'{name}' already exists.",
                "",
                "Do you want to overwrite it?",
            ],
            [
                (
                    "Overwrite",
                    lambda: self._overwrite_template(
                        template
                    ),
                ),
                (
                    "Cancel",
                    self._return_to_list,
                ),
            ],
        )

    def _overwrite_template(
            self,
            template: Dict,
    ):
        """Overwrite an existing template."""

        self._close_dialog()

        self._show_download_view(
            template
        )

        self.downloading = True

        thread = threading.Thread(
            target=self._overwrite_worker,
            args=(template,),
            daemon=True,
        )

        thread.start()

    def _overwrite_worker(
            self,
            template: Dict,
    ):
        """Perform overwrite download."""

        try:
            result = download_template(
                template,
                progress_callback=(
                    self._threadsafe_main_progress
                ),
                reference_progress_callback=(
                    self._threadsafe_reference_progress
                ),
                overwrite=True,
            )

            self._schedule(
                self._download_finished,
                result,
            )

        except Exception as e:
            self._schedule(
                self._download_failed,
                str(e),
            )

    # ==============================================================
    # Manual URL
    # ==============================================================

    def _manual_download(self):
        """Open manual URL download dialog."""

        url_edit = urwid.Edit(
            "URL: "
        )

        name_edit = urwid.Edit(
            "Name: "
        )

        description_edit = urwid.Edit(
            "Description: "
        )

        error_text = urwid.Text(
            "",
            align="center",
        )

        def download(button):
            url = url_edit.edit_text.strip()
            name = name_edit.edit_text.strip()
            description = (
                description_edit.edit_text.strip()
            )

            if not url:
                error_text.set_text(
                    (
                        "error",
                        "URL is required.",
                    )
                )
                self._refresh()
                return

            if not name:
                error_text.set_text(
                    (
                        "error",
                        "Template name is required.",
                    )
                )
                self._refresh()
                return

            template = {
                "name": name,
                "url": url,
                "description": description,
            }

            self._close_dialog()

            self._download_selected_manual(
                template
            )

        def cancel(button):
            self._close_dialog()

        buttons = urwid.Columns(
            [
                urwid.Button(
                    "Download",
                    on_press=download,
                ),
                urwid.Button(
                    "Cancel",
                    on_press=cancel,
                ),
            ],
            dividechars=2,
        )

        content = urwid.Pile(
            [
                self._text(
                    "Download Template from URL",
                    align="center",
                    style="title",
                ),

                urwid.Divider("─"),

                url_edit,
                name_edit,
                description_edit,
                error_text,

                urwid.Divider(),

                self._center(
                    buttons
                ),
            ]
        )

        self._show_dialog(
            urwid.LineBox(
                content,
                title=" Manual Download ",
            )
        )

    def _download_selected_manual(
            self,
            template: Dict,
    ):
        """Download a manually specified template."""

        self.selected_template = template

        self._show_download_view(
            template
        )

        self.downloading = True

        thread = threading.Thread(
            target=self._download_worker,
            args=(template,),
            daemon=True,
        )

        thread.start()

    # ==============================================================
    # Registry
    # ==============================================================

    def _refresh_registry(self):
        """Refresh the remote registry."""

        if self.loading or self.downloading:
            return

        self.loading = True

        self._show_loading()

        thread = threading.Thread(
            target=self._registry_worker,
            daemon=True,
        )

        thread.start()

    def _registry_worker(self):
        """Fetch registry in the background."""
        try:
            templates = fetch_registry()

            self._schedule(
                self._registry_finished,
                templates,
            )

        except Exception as e:
            self._schedule(
                self._registry_failed,
                str(e),
            )

    def _registry_finished(
            self,
            templates: List[Dict],
    ):
        """Handle successful registry refresh."""

        self.loading = False

        self.templates = templates or []

        self.selected_index = 0

        # Make absolutely sure the root widget is active.
        self._close_dialog()

        self._show_list()

        # Explicit redraw after replacing the content.
        self._refresh()

    def _registry_failed(
            self,
            message: str,
    ):
        """Handle registry failure."""

        self.loading = False

        self._show_message(
            "Registry Error",
            [message],
            [
                (
                    "Retry",
                    self._retry_registry,
                ),
                (
                    "Back",
                    self._close_and_back,
                ),
            ],
            error=True,
        )

        self._refresh()

    def _retry_registry(self):
        """Close the error dialog and retry registry loading."""

        # IMPORTANT:
        # Remove the Overlay BEFORE starting the retry.
        self._close_dialog()

        # Let Urwid redraw the root before starting the worker.
        self._refresh()

        self._refresh_registry()

    def _close_and_back(self):
        """Close the dialog and return to the manager."""

        self._close_dialog()

        self._refresh()

        # Call the parent callback after removing the overlay.
        if self.on_close:
            self.on_close()

        self._refresh()

    # ==============================================================
    # Dialogs
    # ==============================================================

    def _show_message(
            self,
            title: str,
            lines: List[str],
            buttons,
            error: bool = False,
    ):
        """Show a centered message dialog."""

        widgets = []

        for line in lines:
            widgets.append(
                self._text(
                    line,
                    align="center",
                    style="error" if error else None,
                )
            )

        widgets.append(
            urwid.Divider()
        )

        button_widgets = []

        for label, callback in buttons:
            # Wrap the callback so the dialog ALWAYS disappears
            # before the actual action executes.
            def button_pressed(
                    button,
                    callback=callback,
            ):
                self._close_dialog()

                # Redraw immediately after removing overlay.
                self._refresh()

                # Schedule the callback on the next event-loop
                # iteration. This prevents Urwid from keeping the
                # old overlay visible.
                self._schedule(
                    callback
                )

            button_widgets.append(
                urwid.Button(
                    label,
                    on_press=button_pressed,
                )
            )

        columns = urwid.Columns(
            button_widgets,
            dividechars=2,
        )

        widgets.append(
            self._center(columns)
        )

        dialog = urwid.LineBox(
            urwid.Pile(widgets),
            title=f" {title} ",
        )

        self._show_dialog(
            dialog
        )

    def _show_dialog(
            self,
            dialog: urwid.Widget,
    ):
        """Display a centered overlay dialog."""
        overlay = urwid.Overlay(
            dialog,
            self.root,
            align="center",
            width=("relative", 70),
            valign="middle",
            height=("relative", 60),
        )

        self.main_loop.widget = overlay
        self._refresh()

    def _close_dialog(self):
        """Close the active dialog."""

        if not self.dialog_open:
            # Still make sure the root is active.
            if self.main_loop.widget is not self.root:
                self.main_loop.widget = self.root
            return

        self.dialog_open = False

        self.main_loop.widget = self.root

        self._refresh()

    # ==============================================================
    # Keyboard
    # ==============================================================

    def handle_input(
            self,
            key: str,
    ):
        """Handle keyboard input from the parent MainLoop."""

        if self.dialog_open:
            # Dialog widgets handle their own keyboard input.
            return False

        if self.loading or self.downloading:
            return True

        if key in ("q", "Q"):
            self.close()
            return True

        if self.current_view == "list":
            return self._handle_list_input(
                key
            )

        if self.current_view == "detail":
            return self._handle_detail_input(
                key
            )

        return False

    def _handle_list_input(
            self,
            key: str,
    ):
        """Handle list-view input."""

        if key == "up":
            if self.templates:
                self.selected_index = max(
                    0,
                    self.selected_index - 1,
                )

                self._update_selection()

            return True

        if key == "down":
            if self.templates:
                self.selected_index = min(
                    len(self.templates) - 1,
                    self.selected_index + 1,
                )

                self._update_selection()

            return True

        if key == "enter":
            if self.templates:
                self._show_detail(
                    self.templates[
                        self.selected_index
                    ]
                )

            return True

        if key in ("u", "U"):
            self._manual_download()
            return True

        if key in ("r", "R"):
            self._refresh_registry()
            return True

        if key in ("b", "B"):
            self.close()
            return True

        return False

    def _handle_detail_input(
            self,
            key: str,
    ):
        """Handle detail-view input."""

        if key in ("b", "B"):
            self._show_list()
            return True

        if key == "enter":
            self._download_selected()
            return True

        if key in ("q", "Q"):
            self.close()
            return True

        return False

    # ==============================================================
    # Helpers
    # ==============================================================

    def _return_to_list(self):
        """Return to template list."""

        self._close_dialog()

        self.selected_index = min(
            self.selected_index,
            max(
                0,
                len(self.templates) - 1,
            ),
        )

        self.current_view = "list"

        self._show_list()

        self._refresh()

    def _set_status(
            self,
            message: str,
    ):
        """Set status bar text."""

        self.status = message

        self.status_bar.original_widget.set_text(
            message
        )

        self._refresh()

    def _refresh(self):
        """
        Force Urwid to redraw.

        This is important when UI changes are triggered by
        an alarm callback or background worker.
        """

        if not self.main_loop:
            return

        try:
            self.main_loop.draw_screen()
        except Exception:
            pass

    @staticmethod
    def _format_size(
            size: int,
    ) -> str:
        """Format bytes as human-readable size."""

        if size < 1024:
            return f"{size} B"

        if size < 1024 ** 2:
            return f"{size / 1024:.1f} KB"

        if size < 1024 ** 3:
            return f"{size / 1024 ** 2:.1f} MB"

        return f"{size / 1024 ** 3:.1f} GB"


def run_template_downloader_tui(
        manager,
        main_loop: urwid.MainLoop,
        on_close: Callable[[], None],
):
    """
    Create and open the downloader inside an existing MainLoop.

    The downloader does NOT start or stop its own MainLoop.
    """

    tui = TemplateDownloaderTUI(
        manager=manager,
        main_loop=main_loop,
        on_close=on_close,
    )

    tui.open()

    return tui