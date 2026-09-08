"""最终 GraphQL 测试"""
from scrapling.fetchers import Fetcher
import json

Fetcher.configure(adaptive=True, huge_tree=True)

GQL_QUERY = """
query SearchNews($keyword: String!, $page: Int!, $sortBy: String!, $pageSize: Int!, $type: [String!]) {
  search(keyword: $keyword, page: $page, sortBy: $sortBy, pageSize: $pageSize, type: $type) {
    total totalPages page result_list { url title formattedDatePublished topics }
  }
}
"""

resp = Fetcher.post(
    'https://cms.bps.org.uk/graphql',
    proxy='http://127.0.0.1:7897',
    timeout=15,
    headers={"Content-Type": "application/json"},
    data=json.dumps({
        "operationName": "SearchNews",
        "variables": {
            "keyword": "", "sortBy": "desc", "page": 0,
            "pageSize": 3, "type": ["news_article"],
        },
        "query": GQL_QUERY,
    }),
)

print(f"Status: {resp.status}")
print(f"Content-Type: {resp.headers.get('content-type', 'N/A')}")
body = resp.body.decode('utf-8', errors='replace')
print(f"Body ({len(resp.body)} bytes): {body[:500]}")

if resp.status == 200:
    try:
        data = json.loads(body)
        search = data.get('data', {}).get('search', {})
        print(f"\nTotal: {search.get('total')}")
        print(f"Pages: {search.get('totalPages')}")
        for r in search.get('result_list', []):
            print(f"  {r.get('title','')[:60]} -> {r.get('url','')}")
    except Exception as e:
        print(f"JSON error: {e}")
