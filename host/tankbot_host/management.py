"""Pure management dispatch; the local API retains its own identity and size guards."""


def experiment_command(authority,operation,value):
    allowed={'status':set(),'start':set(),'stop':set(),'export':set(),'clear':set(),
             'compare':{'snapshot'},'import':{'record'}}
    if operation not in allowed or not isinstance(value,dict) or set(value)!=allowed[operation]:
        raise ValueError('INVALID_EXPERIMENT_REQUEST')
    lab=authority.lab
    if operation=='compare':return lab.compare(value['snapshot'])
    if operation=='import':return lab.import_record(value['record'])
    return getattr(lab,operation)()
