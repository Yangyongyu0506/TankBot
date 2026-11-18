"""Single Start orchestrates existing preflight/deployment without changing tick gates."""
import copy


class PlayerRun:
    def __init__(self, authority, snapshot):
        self.authority = authority
        self.snapshot = copy.deepcopy(snapshot)
        self.phase = 'Checking'
        self.error = None
        self.job_id = None
        try:
            self.job_id = authority.deployment.start('test', snapshot=self.snapshot)['job']['id']
        except (ValueError, SyntaxError, KeyError, TypeError, OSError) as error:
            self.fail(error)

    def fail(self, error):
        self.phase = 'Failed'
        self.error = str(error) if isinstance(error, (ValueError, SyntaxError)) else type(error).__name__ + ': ' + str(error)
        if not isinstance(error, (ValueError, SyntaxError)):
            self.authority.logs.append(self.error + '\n', source='start', stream='error', tick=self.authority.tick)

    def advance(self):
        if self.phase == 'Running' and self.authority.campaign and self.authority.campaign.status != 'active':
            self.phase = 'Finished'
            return
        if self.phase not in ('Checking', 'Starting'):
            return
        manager = self.authority.deployment
        if self.authority.campaign and self.authority.campaign.status != 'active':
            manager.close()
            self.phase = 'Cancelled'
            return
        if manager.job is not None:
            return
        last = manager.last
        if not last or last.get('id') != self.job_id:
            self.phase, self.error = 'Failed', 'START_CANCELLED: 启动任务已结束或被替换'
        elif last['status'] == 'Failed':
            self.phase, self.error = 'Failed', last.get('error', '程序启动失败')
        elif self.phase == 'Checking' and last['status'] == 'Ready':
            try:
                self.job_id = manager.start('deploy', snapshot=self.snapshot)['job']['id']
                self.phase = 'Starting'
            except (ValueError, SyntaxError, KeyError, TypeError, OSError) as error:
                self.fail(error)
        elif self.phase == 'Starting' and last['status'] == 'Active':
            self.phase = 'Running'

    def public(self):
        return {'run_id': self.authority.run_id, 'revision': self.snapshot['revision'],
                'phase': self.phase, 'error': self.error}
