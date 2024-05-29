import argparse
import csv
import datetime
import os

def parseInput(inputFile:str, ignore_row:int):
    '''
    inputFile: str, file path
    ignore_row: int, ignore first n rows
    '''
    extension = os.path.splitext(inputFile)[1]
    
    if extension == '.csv':
        with open(inputFile, 'r') as file:
            reader = csv.reader(file)
            for _ in range(ignore_row):
                next(reader)
            yield from reader

    elif extension == '.xls' or extension == '.xlsx':
        raise NotImplementedError('Excel files are not supported yet')
    else:
        raise ValueError(f'File:{inputFile} extension ({extension}) not supported')
    
class AndroMoneyReader:
    FROM_ACCOUNT_TYPE = {
        'SYSTEM': 'Equity',
        'Transfer': 'Asset',
        'Income': 'Income',
        'Expense': 'Asset',
    }
    TO_ACCOUNT_TYPE = {
        'SYSTEM': 'Asset',
        'Transfer': 'Asset',
        'Income': 'Asset',
        'Expense': 'Expenses',
    }

    def __init__(self, reader, init_date:datetime):
        self.reader = reader
        self.curr_date = init_date

    def __iter__(self):
        return self

    def __next__(self):
        row = next(self.reader)
        result = {
            'id': int(row[0]),
            'currency': row[1],
            'amount': row[2],
            'category': row[3],
            'sub_category': row[4],
            'from_account': row[6],
            'to_account': row[7],
            'remark': row[8],
            'periodic': row[9],
            'project': row[10],
            'payee': row[11],
            'uid': row[12],
            'time': datetime.datetime.strptime(f'{row[5]}{row[13].zfill(4)}', '%Y%m%d%H%M'),
            'status': int(row[14]) if row[14] != '' else None,
        }

        # 0, 1 seems to be fine
        assert result['status'] in [None, 0, 1], f'{result} has status {result["status"]}'

        if result['category'] == 'SYSTEM': # Initial amount
            assert result['sub_category'] == 'INIT_AMOUNT', f'{result} has SYSTEM but not INIT_AMOUNT'
            if float(result['amount']) <= 1e-6: #Skip zero amount
                return self.__next__()
            
            result['payee'] = result['sub_category']
            result['time'] = self.curr_date
            result['from_account'] = 'Opening Balances'
        else:
            self.curr_date = result['time']

            if result['category'] == 'Transfer': # Transfer
                result['payee'] = result['sub_category']
            elif result['category'] == 'Income': # Income
                result['from_account'] = result['sub_category']
            else: # Expense
                result['to_account'] = f"{result['category']}:{result['sub_category']}"
                result['category'] = 'Expense'

        del result['sub_category']

        return result
    
class LedgerWriter:
    def __init__(self, writer, indent:int=4):
        '''
        writer: file
        '''
        self.writer = writer
        self.indent = indent

    def write(self, transaction_date, payee, effective_date=None, changed_account=[], remark='', tags={}):
        '''
        transaction_date: datetime
        payee: string
        (optional) effective_date: datetime
        changed_account: [{
            account: str, 
            (optional) amount: (number: str, currency: str), 
            (optional) effective_dates: [dates, ...],
        }, ...]
        (optional) remark: string
        (optional) tags: {tag: value, ...}
        '''
        # title
        self.writer.write(f'{transaction_date.strftime("%Y-%m-%d")}')
        if effective_date is not None:
            self.file.write(f'={effective_date.strftime("%Y-%m-%d")}')
        self.writer.write(f' * {payee}\n')

        # changed account
        for account in changed_account:
            if 'effective_dates' in account:
                raise NotImplementedError('Effective dates inside account are not supported yet')
            else:
                self.write_single_account(account['account'], account.get('amount', None))

        for tag, value in tags.items():
            self.write_tag(f'{tag}', value)

        self.writer.write(f'\n')

    def write_tag(self, tag, value):
        '''
        tag: str
        value: str
        '''
        tag = '_'.join(tag.split()) # substitute whitespace with underscore
        value = ' '.join(value.split('\n')) # substitute newline with single space
        self.writer.write(f'{" " * self.indent}; :{tag}: {value}\n')

    def write_single_account(self, account, amount=None, effective_date=None):
        '''
        account: str
        amount: (number: str, currency: str)
        (optional) effective_date: datetime
        '''
        print_account = ' '.join(account.split()) # substitute whitespace with single space

        self.writer.write(f'{" " * self.indent}{print_account}')
        if amount is not None:
            self.writer.write(f'  {amount[0]} {amount[1]}')
        if effective_date is not None:
            raise NotImplementedError('Effective dates inside account are not supported yet')
        self.writer.write(f'\n')
        
def generateLedger(reader, outputFile:str):
    '''
    reader: AndroMoneyReader
    outputFile: str
    '''
    with open(outputFile, 'w') as file:
        writer = LedgerWriter(writer=file)
        for row in reader:
            transaction_date = row['time']
            payee = row['payee']
            changed_account = [{
                'account': f"{AndroMoneyReader.TO_ACCOUNT_TYPE[row['category']]}:{row['to_account']}",
                'amount': (row['amount'], row['currency']),
            }, {
                'account': f"{AndroMoneyReader.FROM_ACCOUNT_TYPE[row['category']]}:{row['from_account']}",
            }]
                
            tags = {
                'AndroMoney_uid': row['uid'],
                'AndroMoney_time': row['time'].strftime('%H%M'),
            }
            if row['status'] is not None:
                tags['AndroMoney_status'] = str(row['status'])
            if row['project'] != '':
                tags['AndroMoney_project'] = row['project']
            if row['remark'] != '':
                tags['AndroMoney_remark'] = row['remark']
            # write to ledger
            writer.write(transaction_date=transaction_date, payee=payee, changed_account=changed_account, tags=tags)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Parse AndroMoney CSV export')
    parser.add_argument('input', type=str, help='AndroMoney file')
    parser.add_argument('--output', type=str, help='Output CSV file')
    parser.add_argument('--ignore_row', type=int, help='Ignore first n rows', default=2)
    parser.add_argument('--init_date', type=lambda s: datetime.datetime.strptime(s, '%Y%m%d'), help='Ignore first n rows', default='20160824')
    args = parser.parse_args()

    if args.output is None:
        args.output = os.path.splitext(args.input)[0] + '.ledger'
    reader = parseInput(inputFile=args.input, ignore_row=args.ignore_row)
    reader = AndroMoneyReader(reader, init_date=args.init_date)
    generateLedger(reader, outputFile=args.output)