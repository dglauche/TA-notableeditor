import concurrent.futures
import re
import json
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
from splunklib.searchcommands import dispatch, ReportingCommand, Configuration, Option
import splunklib.binding
import splunklib.client as client
import splunklib.results as results




@Configuration(requires_preop=True)
class EditNotablesCommand(ReportingCommand):
    mode = Option(
        doc=''' **Syntax:** **mode=***[batch|single]*
        **Description:** In batch mode all notables will be processed using the parameter provided with the command. In single mode each notable will be updated using the notable_edit_* fields''',
        require=False,
        default="batch"
    )

    comment = Option(
        doc=''' **Syntax:** **comment=***The comment to set*
        **Description:** The comment all notable will get in batch mode''',
        require=False
    )
    
    status = Option(
        doc=''' **Syntax:** **status=***The status to set*
        **Description:** The status all notable will get in batch mode''',
        require=False
    )

    urgency = Option(
        doc=''' **Syntax:** **status=***The urgency to set*
        **Description:** The urgency all notable will get in batch mode''',
        require=False
    )

    newOwner = Option(
        doc=''' **Syntax:** **status=***The owner to set*
        **Description:** The owner all notable will get in batch mode''',
        require=False
    )

    disposition = Option(
        doc=''' **Syntax:** **status=***The disposition to set*
        **Description:** The disposition all notable will get in batch mode''',
        require=False
    )
    

    # Loops though all records and determines if one of them has a notable_edit_*
    # field
    @staticmethod
    def check_notable_edit_fields(records):
        r = re.compile('notable_edit_.*')

        for record in records:
            relevant_fields = [ k for k in record if r.match(k) ]
            if relevant_fields:
                return True

        return False

    @staticmethod
    def do_requests(session_key, args):
        try:
            req = client.Endpoint(
                    client.connect(token=session_key),
                    '/services/notable_update'
                ).post(body=args)
            
            return json.loads(req['body'].readall().decode())

        except splunklib.binding.HTTPError as e:
            if isinstance(args['ruleUIDs'], str):
                failure_count = 1
            else:
                failure_count = len(args['ruleUIDs'])

            return {
                'details': {},
                'success_count': 0,
                'failure_count': failure_count,
                'warnings': str(e),
                'success': False,
                'message': 'Notable editing failed'
            }

        

    
    # retrieves valid notable statis, urgencies & dispositions
    def set_valid_stati(self):
        service = client.connect(token=self._metadata.searchinfo.session_key)

        stati = service.kvstore['reviewstatuses'].data.query()

        self.valid_notable_stati = {}
        self.valid_notable_urgencies = []
        self.valid_notable_dispositions = {}
        for status in stati:
            if status['disabled']:
                continue

            if status['status_type'] == 'notable':
                self.valid_notable_stati[status['label'].lower()] = status['status']
                continue

            if status['status_type'] == 'disposition':
                self.valid_notable_dispositions[status['label'].lower()] = status
                continue

        
        urgencies_job = results.JSONResultsReader(
            service.jobs.oneshot(
                '| inputlookup urgency_lookup | stats count by urgency | fields urgency',
                output_mode='json'
            )
        )

        for result in urgencies_job:
            if isinstance(result, dict):
                self.valid_notable_urgencies.append(result['urgency'])


    @Configuration()
    def map(self, records):
        return records


    def reduce(self, records):
        self.set_valid_stati()

        records = list(records)

        # Do all edits at once
        if self.mode=="batch":
            if self.check_notable_edit_fields(records):
                raise Exception('One of your events has a notable_edit_.* field which is not allowed in batch mode. You might want to use mode=single')

            args = {}
            if self.comment:
                args['comment'] = self.comment

            if self.status:
                if not self.status.lower() in self.valid_notable_stati.keys():
                    raise Exception(f"The status value \"{self.status}\" is not valid. Valid ones are: {list(self.valid_notable_stati.keys())}")

                args['status'] = self.valid_notable_stati[self.status.lower()]

            if self.urgency:
                if not self.urgency.lower() in self.valid_notable_urgencies:
                    raise Exception(f"The urgency value \"{self.urgency}\" is not valid. Valid ones are: {self.valid_notable_urgencies}")

                args['urgency'] = self.urgency

            if self.newOwner:
                args['newOwner'] = self.newOwner

            if self.disposition:
                if not self.disposition.lower() in self.valid_notable_dispositions:
                    raise Exception(f"The disposition value \"{self.disposition}\" is not valid. Valid ones are: {list(self.valid_notable_dispositions.keys())}")

                args['disposition'] = self.valid_notable_dispositions[self.disposition.lower()]['status']
                

            if not args:
                raise Exception('Please provide at least one of the options comment, status, urgency, newOwner or use the inline edit feature using for example "notable_edit_comment"')
            

            args['ruleUIDs'] = [ record['event_id'] for record in records if 'event_id' in record ]
            args['ruleUIDs'].extend(
                [ record['rule_id'] for record in records if 'rule_id' in record ]
            )
            args['ruleUIDs'] = list(set(args['ruleUIDs']))

            yield self.do_requests(
                session_key=self._metadata.searchinfo.session_key,
                args=args
            )
        
        # different settings need different requests
        elif self.mode=="single":
            request_packets = []

            if self.comment or self.status or self.urgency or self.newOwner or self.disposition:
                raise Exception('No parameters are allowed when using the command in mode=single. Use "notable_edit_comment" for example')

            # collect all infos for the requests
            for record in records:
                args = {}
                if 'notable_edit_comment' in record and record['notable_edit_comment']:
                    args['comment'] = record['notable_edit_comment']

                if 'notable_edit_status' in record and record['notable_edit_status']:
                    if not record['notable_edit_status'].lower() in self.valid_notable_stati.keys():
                        raise Exception(f"The status value \"{record['notable_edit_status']}\" is not valid. Valid ones are: {list(self.valid_notable_stati.keys())}")
                        
                    args['status'] = self.valid_notable_stati[record['notable_edit_status'].lower()]

                if 'notable_edit_urgency' in record and record['notable_edit_urgency']:
                    if not record['notable_edit_urgency'].lower() in self.valid_notable_urgencies:
                        raise Exception(f"The urgency value {record['notable_edit_urgency']} is not valid. Valid ones are: {self.valid_notable_urgencies}")

                    args['urgency'] = record['notable_edit_urgency']

                if 'notable_edit_newOwner' in record and record['notable_edit_newOwner']:
                    args['newOwner'] = record['notable_edit_newOwner']

                if 'notable_edit_disposition' in record and record['notable_edit_disposition']:
                    if not record['notable_edit_disposition'].lower() in self.valid_notable_dispositions:
                        raise Exception(f"The disposition value \"{record['notable_edit_disposition']}\" is not valid. Valid ones are: {list(self.valid_notable_dispositions.keys())}")

                    args['disposition'] = self.valid_notable_dispositions[record['notable_edit_disposition'].lower()]['status']

                if not args:
                    # Seems like now modification should be made to this notable
                    continue

                if 'event_id' in record and record['event_id']:
                    args['ruleUIDs'] = record['event_id']

                if 'rule_id' in record and record['rule_id']:
                    args['ruleUIDs'] = record['rule_id']

                if not 'ruleUIDs' in args:
                    self.logger.warn("The event does not have an event_id or rule_id. There for processing can not be done.")

                request_packets.append(args)
                
            # execute requests
            res = []
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = {
                    executor.submit(
                        self.do_requests,
                        session_key=self._metadata.searchinfo.session_key,
                        args=item
                    ): item for item in request_packets
                }

                for future in concurrent.futures.as_completed(futures):
                    res.append(future.result())

            for r in res:
                yield r

        else:
            raise Exception('One of your events has a notable_edit_.* field which is not allowed in batch mode')
            

dispatch(EditNotablesCommand, sys.argv, sys.stdin, sys.stdout, __name__)
