from splunklib.searchcommands import dispatch, ReportingCommand, Configuration, Option
import splunklib.client as client
import sys
import json

STATUS_MAP = {
    'new': 1,
    'in progress': 2,
    'pending': 3,
    'resolved': 4,
    'closed': 5
}

VALID_URGENCIES = [
    'critical', 'high',
    'medium', 'low',
    'informational'
]

@Configuration(requires_preop=True)
class EditNotablesCommand(ReportingCommand):
    comment = Option(
        doc='The comment to set',
        require=False)
    
    status = Option(
        doc='The status to set',
        require=False)

    urgency = Option(
        doc='The urgency to set',
        require=False)

    newOwner = Option(
        doc='The new owner of the notables',
        require=False)

    @Configuration()
    def map(self, records):
        return records

    def reduce(self, records):
        args = {}
        if self.comment:
            args['comment'] = self.comment

        if self.status and self.status.lower() in STATUS_MAP.keys():
            args['status'] = STATUS_MAP[self.status.lower()]

        if self.urgency:
            args['urgency'] = self.urgency

        if self.newOwner:
            args['newOwner'] = self.newOwner

        if not self.urgency.lower() in VALID_URGENCIES:
            yield {'result': f"The urgency value provided is not valid. Valid ones are: {VALID_URGENCIES}" }

        if not args:
            yield {'result': 'Please provide at least one of the options comment, status, urgency, newOwner' }
            return

        event_ids = []
        for record in records:
            event_ids.append(record['event_id'])

        args['ruleUIDs'] = event_ids
        req = client.Endpoint(
            client.connect(token=self._metadata.searchinfo.session_key),
            '/services/notable_update'
        ).post(body=args)

        yield json.loads(req['body'].readall().decode())

dispatch(EditNotablesCommand, sys.argv, sys.stdin, sys.stdout, __name__)