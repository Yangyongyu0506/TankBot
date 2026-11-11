"""Shared resource catalogue and pure management dispatch; transports keep their own guards."""
UI_RESOURCES = (
    'index.html','app.js','style.css','rendering.js','browser-client.js','workspace-ui.js',
    'file-tree.js','workspace-dialog.js','campaign-ui.js','level-tree.js','live-metrics.js',
    'control-feedback.js','learning-ui.js','gamepad.js','settings-ui.js','keyboard.js',
    'visualization.js','localization-view.js','navigation-view.js','runtime-logs.js',
    'robot-graph.js','map-preview.js','experiment-ui.js','timing-ui.js','storage-ui.js',
    'path-view.js',
    'global-planning-view.js','scan-view.js',
)
CORE_RESOURCES = ('core-worker.js','wasm-core.js','python-loader.js','python-bootstrap.js')
ROBOT_RESOURCES = ('runtime-frame.html','runtime-frame.js','robot-worker.js','python-bootstrap.js')


def experiment_command(authority,operation,value):
    allowed={'status':set(),'start':set(),'stop':set(),'export':set(),'clear':set(),
             'compare':{'snapshot'},'import':{'record'}}
    if operation not in allowed or not isinstance(value,dict) or set(value)!=allowed[operation]:
        raise ValueError('INVALID_EXPERIMENT_REQUEST')
    lab=authority.lab
    if operation=='compare':return lab.compare(value['snapshot'])
    if operation=='import':return lab.import_record(value['record'])
    return getattr(lab,operation)()
