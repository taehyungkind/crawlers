from __future__ import unicode_literals
from datetime import date
from itertools import chain
import re

from scrapy.http import Request
from scrapy.selector import Selector
from scrapy.spider import Spider

from likms.items import BillHtmlItem
from likms.rules import likms_url, XPATHS
from likms.utils import sel_to_str


__all__ = ['NewBillSpider']


ALL = 150
word_re = re.compile(r'\w+')


class NewBillSpider(Spider):
    name = 'new-bills'
    allowed_domains = ['likms.assembly.go.kr']
    headers = {
        'Referer': 'http://likms.assembly.go.kr'
    }

    def __init__(self, *args, **kwargs):
        super(NewBillSpider, self).__init__(*args, **kwargs)
        self.date_since = kwargs.get('date_since')

    ## Step 1: retrieve new bill id list
    def start_requests(self):
        date_since = self.date_since or date.today().isoformat()
        return [Request(url=likms_url('new-bill-list',
                                      date_since=date_since,
                                      size=ALL),
                        headers=self.headers,
                        callback=self.parse_new_bills)]

    def parse_new_bills(self, response):
        sel = Selector(response)
        bills_sel = sel.xpath(XPATHS['new-bill-list'])
        bill_id_pairs = (self._parse_new_bill_id_pair(bill_sel)
                         for bill_sel in bills_sel)
        bill_id_pairs = filter(None, bill_id_pairs)
        return self.requests_for_bills(bill_id_pairs)

    ## Step 2: crawl bills
    def requests_for_bills(self, bill_id_pairs):
        # Flatten [[Request, ...], [Request, ...], ...] -> [Request, ...]
        return chain(*(self.requests_for_single_bill(bill_id, link_id)
                       for bill_id, link_id in bill_id_pairs))

    bill_pagetypes = ('bill-spec', 'bill-summary', 'bill-proposers', 'bill-withdrawers')
    def requests_for_single_bill(self, bill_id, link_id):
        return (self.bill_page_request(bill_id, link_id, pagetype)
                for pagetype in self.bill_pagetypes)

    def bill_page_request(self, bill_id, link_id, pagetype):
        meta = dict(bill_id=bill_id, pagetype=pagetype)
        return Request(url=likms_url(pagetype, link_id=link_id),
                       headers=self.headers,
                       meta=meta,
                       callback=self.parse_bill_page)

    def parse_bill_page(self, response):
        bill_id, pagetype = [response.meta[k] for k in ('bill_id', 'pagetype')]
        yield BillHtmlItem(bill_id, pagetype, body=response.body)

    def _parse_new_bill_id_pair(self, sel):
        columns = sel.xpath(XPATHS['columns'])
        if len(columns) != 8:
            return

        bill_id = sel_to_str(columns[0].xpath('text()'))
        link_id = word_re.findall(columns[1].xpath('a/@href').extract()[0])[2]
        return bill_id, link_id
