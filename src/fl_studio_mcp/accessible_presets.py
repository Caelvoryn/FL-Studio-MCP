"""Named accessibility controls as a last-resort preset adapter, never images.

Only the observed Pianoteq9 profile is enabled. UIA support must not be inferred
for Serum, Nexus, or any other plugin merely because they are VSTs.
"""
from .desktop import wait_for
from .workflow import WorkflowError


def parse_current_label(label, prefix='Current preset: '):
    if not isinstance(label,str) or not label.startswith(prefix):
        raise WorkflowError('ACCESSIBILITY_LAYOUT','Unrecognized current-preset label')
    value=label[len(prefix):]
    modified=value.endswith(' (modified)')
    name=value[:-11] if modified else value
    if not name:
        raise WorkflowError('ACCESSIBILITY_LAYOUT','Empty preset label')
    return dict(name=name,modified=modified,raw_label=label)


def unique_named(controls,name):
    matches=[c for c in controls if c.window_text()==name]
    if len(matches)!=1:
        raise WorkflowError('ACCESSIBILITY_NOT_UNIQUE','Exact named control must occur once',name=name,count=len(matches))
    return matches[0]


class AccessiblePresets:
    def __init__(self,host,expected_channel,plugin_name):
        if plugin_name!='Pianoteq 9':
            raise WorkflowError('NO_ACCESSIBILITY_PROFILE','Only Pianoteq9 has been verified')
        self.host=host
        candidates=[w for w in host.uia.window(handle=host.main.handle).descendants()
                    if w.class_name()=='TPluginForm' and w.is_visible()
                    and w.window_text().startswith(expected_channel+'\ue5a0')]
        if len(candidates)!=1:
            raise WorkflowError('PLUGIN_WINDOW_NOT_UNIQUE','Open exactly one matching hosted plugin window; no screenshot/mouse fallback',count=len(candidates))
        self.plugin=candidates[0]
        roots=[w for w in self.plugin.descendants() if w.class_name().startswith('JUCE_')]
        if len(roots)!=1:
            raise WorkflowError('ACCESSIBILITY_LAYOUT','Expected one hosted JUCE accessibility root')
        self.juce_class=roots[0].class_name()

    def _button(self):
        buttons=[w for w in self.plugin.descendants(control_type='Button') if w.window_text().startswith('Current preset: ')]
        if len(buttons)!=1:
            raise WorkflowError('ACCESSIBILITY_LAYOUT','No unique current-preset accessibility label')
        return buttons[0]

    def read(self):
        return dict(**parse_current_label(self._button().window_text()),
                    source='hosted plugin UI Automation Name property',plugin_window=self.plugin.handle)

    def _menu_items(self):
        return [c for w in self.host.uia.windows(process=self.host.pid,class_name=self.juce_class)
                if w.is_visible() and w.window_text()=='JUCE Application'
                for c in w.descendants(control_type='MenuItem')]

    def select(self,menu_path,expected_current):
        if not isinstance(menu_path,list) or not 1<=len(menu_path)<=4 or any(not isinstance(s,str) or not s for s in menu_path):
            raise WorkflowError('INVALID_ARGUMENT','Explicit exact menu path of1..4 names required')
        before=self.read()
        if before['name']!=expected_current:
            raise WorkflowError('STALE_PRESET','Current preset differs',actual=before)
        if self._menu_items():
            raise WorkflowError('GUI_BLOCKED','Existing preset popup; inspect it before another non-idempotent action')
        self._button().iface_invoke.Invoke()
        try:
            for index,name in enumerate(menu_path):
                wait_for(lambda: next((c for c in self._menu_items() if c.window_text()==name),None),timeout=5,description='named preset menu item')
                item=unique_named(self._menu_items(),name)
                if index<len(menu_path)-1:
                    # Expand the named submenu instead of invoking it as a leaf.
                    # An observed Invoke path opened an unrelated submenu; that
                    # attempt timed out and was NOT treated as preset success.
                    item.iface_expand_collapse.Expand()
                else:
                    item.iface_invoke.Invoke()
            after=wait_for(lambda: (value if (value:=self.read())['name']==menu_path[-1] else None),timeout=10,description='actual selected preset name')
        except WorkflowError as exc:
            exc.details['accessible_menu_items']=[c.window_text() for c in self._menu_items()][:80]
            exc.details['recovery']='Do not retry blindly; inspect/dismiss the identified popup and read current preset'
            raise
        return dict(ok=True,verified=True,before=before,after=after,execution_kind='UIA_InvokePattern_fallback',
                    preset_name_verified=True,model_menu_path=menu_path[:-1],
                    model_name_verified=False,persistence_verified=False,screenshots=0,mouse_operations=0,
                    limitation='Actual preset label verified; model menu path selected, separate internal model field not exposed. Not a host parameter/Program Change operation.')
