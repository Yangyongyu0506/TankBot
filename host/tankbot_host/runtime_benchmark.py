"""Private, payload-free timing deltas for a trusted in-process benchmark driver.

This helper is never routed through the Godot API or given to player Python.
"""

def snapshot(authority):
    campaign=authority.campaign
    return {'run_id':authority.run_id,'tick':authority.tick,'ready':authority.worker.poll_ready(),
            'profile':authority.runtime_profile.public(),'runtime_fault':authority.worker.fault,
            'attempt_status':campaign.status if campaign else None,
            'result':campaign.result if campaign and campaign.status!='active' else None,
            'startup_result':authority.worker.startup_result,
            'timing':authority.worker.timing.drain()}
