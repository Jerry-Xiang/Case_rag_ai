# qwen_agent/tools/es_retrieval.py
import json
import logging
from typing import Dict, List, Optional
from qwen_agent.tools.base import BaseTool, register_tool
from qwen_agent.tools.doc_parser import DocParser
from qwen_agent.tools.retrieval import Retrieval
from qwen_agent.utils.utils import print_traceback
from qwen_agent.searcher.elasticsearch_searcher import ElasticsearchSearcher
from qwen_agent.settings import DEFAULT_MAX_REF_TOKEN

logger = logging.getLogger(__name__)

class ESRetrievalTool(BaseTool):
    """
    一个使用 Elasticsearch 作为后端的检索工具。
    当 ES 连接失败时，自动降级到文档解析检索。
    """
    name = 'retrieval'
    description = '从 Elasticsearch 索引的文档中检索与用户查询相关的内容。'
    parameters = [{
        'name': 'query',
        'type': 'string',
        'description': '用户查询的关键词或问题',
        'required': True
    }, {
        'name': 'files',
        'type': 'list',
        'description': '需要检索的文件列表',
        'required': True
    }]

    def __init__(self, cfg: dict = None):
        super().__init__(cfg)
        self.cfg = cfg or {}
        self.max_ref_token = self.cfg.get('max_ref_token', DEFAULT_MAX_REF_TOKEN)
        
        self.es_available = False
        self.searcher: Optional[ElasticsearchSearcher] = None
        self.fallback_retrieval: Optional[Retrieval] = None
        
        self._init_search_backend()

    def _init_search_backend(self):
        """初始化搜索后端，优先使用 ES，失败则降级到文档解析检索。"""
        print("\n" + "="*60)
        print("[ESRetrievalTool] 初始化搜索后端...")
        print("="*60)
        
        try:
            print("[ESRetrievalTool] 尝试连接 Elasticsearch...")
            self.searcher = ElasticsearchSearcher(cfg=self.cfg)
            
            if self.searcher and self.searcher.client:
                self.es_available = True
                print("[ESRetrievalTool] ✓ Elasticsearch 连接成功！将使用 ES 作为检索后端。")
                print(f"[ESRetrievalTool]   - ES 地址: {self.searcher.host}:{self.searcher.port}")
                print(f"[ESRetrievalTool]   - 索引名称: {self.searcher.index_name}")
            else:
                self.es_available = False
                print("[ESRetrievalTool] ✗ Elasticsearch 连接失败！")
                
        except Exception as e:
            self.es_available = False
            print(f"[ESRetrievalTool] ✗ Elasticsearch 初始化异常: {e}")
        
        if not self.es_available:
            print("[ESRetrievalTool] 🔄 降级到文档解析检索模式 (Retrieval)")
            try:
                self.fallback_retrieval = Retrieval(cfg=self.cfg)
                print("[ESRetrievalTool] ✓ 文档解析检索工具初始化成功！")
            except Exception as e:
                print(f"[ESRetrievalTool] ✗ 文档解析检索工具初始化失败: {e}")
        
        print("="*60 + "\n")

    def call(self, params: dict, **kwargs) -> str:
        """
        工具调用的主入口。
        如果 ES 可用，使用 ES 进行检索；否则降级到文档解析检索。
        """
        query_input = params.get('query', '')
        files = params.get('files', [])
        
        print(f"\n[ESRetrievalTool] 收到检索请求:")
        print(f"  - 查询: {query_input[:100]}..." if len(query_input) > 100 else f"  - 查询: {query_input}")
        print(f"  - 文件数量: {len(files)}")
        print(f"  - ES 可用: {'是' if self.es_available else '否'}")
        
        if self.es_available and self.searcher:
            print("[ESRetrievalTool] → 使用 Elasticsearch 进行检索")
            return self._call_es(query_input, files, **kwargs)
        else:
            print("[ESRetrievalTool] → 使用文档解析检索进行兜底")
            return self._call_fallback(query_input, files, **kwargs)

    def _call_es(self, query_input: str, files: list, **kwargs) -> str:
        """使用 Elasticsearch 进行检索。"""
        try:
            if files and isinstance(files, list):
                print(f"[ESRetrievalTool] 正在索引 {len(files)} 个文件到 ES...")
                self.searcher.index_files(files)
            
            if not query_input:
                return json.dumps([], ensure_ascii=False)
            
            query = self._parse_query(query_input)
            
            print(f"[ESRetrievalTool] 在 ES 中搜索: '{query[:50]}...'" if len(query) > 50 else f"[ESRetrievalTool] 在 ES 中搜索: '{query}'")
            search_results = self.searcher.search(query, max_ref_token=self.max_ref_token)
            
            formatted_results = [
                {
                    'url': hit.get('_source', {}).get('source', 'N/A'),
                    'text': hit.get('_source', {}).get('content', '')
                } for hit in search_results
            ]
            
            print(f"[ESRetrievalTool] ES 搜索完成，返回 {len(formatted_results)} 条结果")
            return json.dumps(formatted_results, ensure_ascii=False)
            
        except Exception as e:
            print(f"[ESRetrievalTool] ES 检索失败: {e}")
            print("[ESRetrievalTool] 降级到文档解析检索...")
            return self._call_fallback(query_input, files, **kwargs)

    def _call_fallback(self, query_input: str, files: list, **kwargs) -> str:
        """使用文档解析检索进行兜底。"""
        if not self.fallback_retrieval:
            print("[ESRetrievalTool] ✗ 文档解析检索工具不可用，返回空结果")
            return json.dumps([], ensure_ascii=False)
        
        try:
            print("[ESRetrievalTool] 正在使用文档解析检索...")
            
            params = {
                'query': query_input,
                'files': files
            }
            
            results = self.fallback_retrieval.call(params, **kwargs)
            
            if isinstance(results, list):
                result_str = json.dumps(results, ensure_ascii=False)
            elif isinstance(results, str):
                result_str = results
            else:
                result_str = json.dumps([], ensure_ascii=False)
            
            print(f"[ESRetrievalTool] 文档解析检索完成，返回 {len(results) if isinstance(results, list) else '未知'} 条结果")
            return result_str
            
        except Exception as e:
            print(f"[ESRetrievalTool] 文档解析检索失败: {e}")
            return json.dumps([], ensure_ascii=False)

    def _parse_query(self, query_input: str) -> str:
        """解析来自 Memory 模块的复杂 JSON 查询。"""
        try:
            query_obj = json.loads(query_input)
            if isinstance(query_obj, dict):
                query = query_obj.get('text', '')
                if not query and 'keywords_zh' in query_obj and query_obj['keywords_zh']:
                    query = ' '.join(query_obj['keywords_zh'])
                if not query:
                    query = query_input
            else:
                query = query_input
        except (json.JSONDecodeError, TypeError):
            query = query_input
        return query

    def _format_error(self, error_message: str) -> str:
        return json.dumps([{'error': error_message}], ensure_ascii=False) 