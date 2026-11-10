"""Read-only, payload-free timing deltas for the explicitly enabled local QA harness."""

def snapshot(authority):
    if not authority.config['browser']['probe_enabled']:
        raise ValueError('UNAUTHORIZED')
    campaign=authority.campaign
    return {'run_id':authority.run_id,'tick':authority.tick,'ready':authority.worker.poll_ready(),
            'profile':authority.runtime_profile.public(),'runtime_fault':authority.worker.fault,
            'attempt_status':campaign.status if campaign else None,
            'result':campaign.result if campaign and campaign.status!='active' else None,
            'startup_result':authority.worker.startup_result,
            'timing':authority.worker.timing.drain()}
