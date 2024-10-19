import pickle
import difflib
import pathlib
import zlib

import idaapi
import ida_kernwin
import ida_idaapi
import ida_name
from PyQt5 import QtWidgets


USE_CACHE = True
DOC_DB_PATH = pathlib.Path(__file__).parent / 'msdn.db'
HOTKEY = 'Ctrl-Shift-B'


class DocsDBView(object):
    def __init__(self, filepath: str, use_cache: bool = True):
        self.use_cache = use_cache
        self._data = {}
        self._keys = {}
        if not pathlib.Path(filepath).exists():
            raise FileNotFoundError('Database file not found')
        self._filepath = filepath

    def data(self) -> dict:
        if not self._data:
            with open(self._filepath, 'rb') as handle:
                self._data = pickle.load(handle)
        return self._data

    def __getitem__(self, key: str) -> str:
        value = bytes(self.data()[key])
        if not self.use_cache:
            self._data.clear()
        return zlib.decompress(value).decode()

    def keys(self) -> set:
        if not self._keys:
            self._keys = set(self.data())
            if not self.use_cache:
                self._cache.clear()
        return self._keys       


class MSDN(idaapi.PluginForm):
    widget_name = 'MSDN Docs'
    options = (
        ida_kernwin.PluginForm.WOPN_MENU
        | ida_kernwin.PluginForm.WOPN_ONTOP
        | ida_kernwin.PluginForm.WOPN_RESTORE
        | ida_kernwin.PluginForm.WOPN_PERSIST
        | ida_kernwin.PluginForm.WCLS_CLOSE_LATER
    )

    def OnCreate(self, form):
        self.closed = False
        self.parent = self.FormToPyQtWidget(form)
        self.main_layout = QtWidgets.QVBoxLayout()
        self.markdown_viewer_label = QtWidgets.QLabel()
        self.markdown_viewer = QtWidgets.QTextEdit()
        self.markdown_viewer.setReadOnly(True)
        self.main_layout.addWidget(self.markdown_viewer)
        self.parent.setLayout(self.main_layout)
        
    def OnClose(self, form):
        del form
        self.closed = True

    def Show(self):
        super().Show(self.widget_name, options=self.options)

    def Update(self, content):
        self.markdown_viewer.setMarkdown(content)


class MSDNChoose(idaapi.Choose):
    def __init__(self,):
        super().__init__(
            title="Select API",
            cols=[["API Name", 50]],
            flags=idaapi.Choose.CH_RESTORE,
            embedded=False,
        )
        self.options = []

    def OnGetSize(self) -> int:
        return len(self.options)

    def OnGetLine(self, n: int) -> list:
        return [self.options[n]]

    def Pick(self, options: list):
        self.options = options
        index = super().Show(modal=True)
        if index == -1:
            return None
        return self.options[index]


class MSDNPlugin(ida_idaapi.plugin_t):
    flags = ida_idaapi.PLUGIN_MOD
    comment = "API MSDN Docs"
    help = ""
    wanted_name = "API MSDN Docs"
    wanted_hotkey = "Ctrl-Shift-Z"

    def init(self):
        self.viewer = MSDN()
        self.choose = MSDNChoose()

        try:
            self.db = DocsDBView(filepath=str(DOC_DB_PATH), use_cache=USE_CACHE)
        except FileNotFoundError as e:
            ida_kernwin.msg(f'{e}\n')
            return idaapi.PLUGIN_SKIP

        self.cache = set(self.db.keys())
        return ida_idaapi.PLUGIN_KEEP

    def run(self, arg):
        api_name = self.get_api_name()
        if not api_name:
            ida_kernwin.msg('description not found\n')
            return

        description = self.db[api_name]
        widget = idaapi.find_widget(self.viewer.widget_name)
        if widget:
            idaapi.activate_widget(widget, True)
        else:
            self.viewer.Show()
        self.viewer.Update(content=description)
 
    def term(self):
        pass

    def get_api_name(self):
        api_name = self.get_api_name_from_selection()
        if not api_name:
            ida_kernwin.msg('invalid selection\n')
            return None

        if api_name not in self.cache:
            matches = difflib.get_close_matches(api_name, self.cache)
            if len(matches) == 0:
                return None
            elif len(matches) == 1:
                return matches[0]
            else:
                api_name = self.choose.Pick(matches)

        return api_name

    @staticmethod
    def get_api_name_from_selection():
        v = ida_kernwin.get_current_viewer()
        highlight = ida_kernwin.get_highlight(v)
        if not highlight:
            return None 

        name, _ = highlight

        # remove common prefixes
        prefixes = [ida_name.FUNC_IMPORT_PREFIX, 'cs:', 'ds:', 'j_']
        for prefix in prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        
        # select function call in decompiler view
        pos = name.find('(')
        if pos != -1:
            name = name[:pos]

        return name


plugin = MSDNPlugin()


def PLUGIN_ENTRY():
    global plugin
    return plugin
