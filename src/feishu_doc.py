# feishu_doc.py
# -*- coding: utf-8 -*-
import logging
import json
import requests
import lark_oapi as lark
from lark_oapi.api.docx.v1 import *
from typing import List, Dict, Any, Optional
from src.config import get_config

logger = logging.getLogger(__name__)

# 云盘根目录的固定 token（来自 drive API 实际返回）
DRIVE_ROOT_TOKEN = "nodcnAFsxRoLAEXFYq4nkfBpAoc"


class FeishuDocManager:
    """飞书云文档管理器 (基于 lark-oapi SDK + REST API 补充)

    策略：
    1. Bot 在飞书云盘根目录自动创建「DSA自动日报」文件夹（一次）
    2. 后续所有报告文档都创建在该文件夹下
    3. 不再依赖用户手动创建文件夹和配置 folder_token
    """

    DEFAULT_FOLDER_NAME = "DSA自动日报"

    TRACKING_FOLDER_NAME = "个股分析追踪"

    def __init__(self):
        self.config = get_config()
        self.app_id = self.config.feishu_app_id
        self.app_secret = self.config.feishu_app_secret
        self._tenant_token = None
        self._folder_token = None
        self._tracking_folder_token = None

        if self.is_configured():
            self.client = lark.Client.builder() \
                .app_id(self.app_id) \
                .app_secret(self.app_secret) \
                .log_level(lark.LogLevel.INFO) \
                .build()
        else:
            self.client = None

    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_secret)

    def _get_tenant_token(self) -> Optional[str]:
        """获取 tenant_access_token（带缓存）"""
        if self._tenant_token:
            return self._tenant_token
        try:
            r = requests.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                timeout=10,
            )
            data = r.json()
            self._tenant_token = data.get("tenant_access_token")
            return self._tenant_token
        except Exception as e:
            logger.error(f"获取 tenant_access_token 失败: {e}")
            return None

    def _rest_headers(self) -> dict:
        token = self._get_tenant_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_or_create_folder(self) -> Optional[str]:
        """获取或创建 DSA 自动日报文件夹，返回 folder_token"""
        if self._folder_token:
            return self._folder_token

        if not self.is_configured():
            return None

        folder_name = getattr(self.config, "feishu_doc_folder_name", None) or self.DEFAULT_FOLDER_NAME

        try:
            # 1. 列出现有文件夹，查找同名
            headers = self._rest_headers()
            if not headers.get("Authorization"):
                return None

            r = requests.get(
                "https://open.feishu.cn/open-apis/drive/v1/files",
                headers={"Authorization": headers["Authorization"]},
                params={"page_size": 50},
                timeout=10,
            )
            if r.status_code != 200:
                logger.error(f"列出云盘文件失败: {r.status_code}")
                return None

            files = r.json().get("data", {}).get("files", [])
            for f in files:
                if f.get("type") == "folder" and f.get("name") == folder_name:
                    self._folder_token = f["token"]
                    logger.info(f"找到已有文件夹「{folder_name}」: {self._folder_token}")
                    return self._folder_token

            # 2. 不存在则创建
            logger.info(f"文件夹「{folder_name}」不存在，正在创建...")
            r2 = requests.post(
                "https://open.feishu.cn/open-apis/drive/v1/files/create_folder",
                headers=headers,
                json={"name": folder_name, "folder_token": DRIVE_ROOT_TOKEN},
                timeout=10,
            )
            if r2.status_code == 200 and r2.json().get("code") == 0:
                self._folder_token = r2.json()["data"]["token"]
                logger.info(f"文件夹「{folder_name}」创建成功: {self._folder_token}")
                return self._folder_token
            else:
                logger.error(f"创建文件夹失败: {r2.text[:300]}")
                return None

        except Exception as e:
            logger.error(f"获取/创建文件夹异常: {e}")
            return None

    def create_daily_doc(self, title: str, content_md: str) -> Optional[str]:
        """创建日报文档（自动放入 DSA自动日报 文件夹）"""
        if not self.client or not self.is_configured():
            logger.warning("飞书 SDK 未初始化或配置缺失，跳过创建")
            return None

        # 获取/创建文件夹
        folder_token = self.get_or_create_folder()
        if not folder_token:
            logger.warning("无法获取目标文件夹，将文档创建到默认空间")
            folder_token = None

        try:
            # 1. 创建文档
            body_builder = CreateDocumentRequestBody.builder().title(title)
            if folder_token:
                body_builder = body_builder.folder_token(folder_token)

            create_request = CreateDocumentRequest.builder() \
                .request_body(body_builder.build()) \
                .build()

            response = self.client.docx.v1.document.create(create_request)

            if not response.success():
                logger.error(f"创建文档失败: {response.code} - {response.msg}")
                return None

            doc_id = response.data.document.document_id
            doc_url = f"https://feishu.cn/docx/{doc_id}"
            logger.info(f"飞书文档创建成功: {title} (ID: {doc_id})")

            # 2. 解析 Markdown 并写入内容
            blocks = self._markdown_to_sdk_blocks(content_md)
            batch_size = 50
            doc_block_id = doc_id

            for i in range(0, len(blocks), batch_size):
                batch_blocks = blocks[i:i + batch_size]
                batch_add_request = CreateDocumentBlockChildrenRequest.builder() \
                    .document_id(doc_id) \
                    .block_id(doc_block_id) \
                    .request_body(CreateDocumentBlockChildrenRequestBody.builder()
                                  .children(batch_blocks)
                                  .index(-1)
                                  .build()) \
                    .build()
                write_resp = self.client.docx.v1.document_block_children.create(batch_add_request)
                if not write_resp.success():
                    logger.error(f"写入文档内容失败(批次{i}): {write_resp.code} - {write_resp.msg}")

            logger.info("文档内容写入完成")
            return doc_url

        except Exception as e:
            logger.error(f"飞书文档操作异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    # ── 个股分析追踪文档 ───────────────────────────────────────

    def get_or_create_tracking_folder(self) -> Optional[str]:
        """获取或创建「个股分析追踪」子文件夹（位于 DSA自动日报 下）"""
        if self._tracking_folder_token:
            return self._tracking_folder_token

        parent_token = self.get_or_create_folder()
        if not parent_token:
            return None

        headers = self._rest_headers()
        if not headers.get("Authorization"):
            return None

        try:
            # 查找已存在的追踪文件夹
            r = requests.get(
                "https://open.feishu.cn/open-apis/drive/v1/files",
                headers={"Authorization": headers["Authorization"]},
                params={"folder_token": parent_token, "page_size": 50},
                timeout=10,
            )
            if r.status_code == 200:
                for f in r.json().get("data", {}).get("files", []):
                    if f.get("type") == "folder" and f.get("name") == self.TRACKING_FOLDER_NAME:
                        self._tracking_folder_token = f["token"]
                        logger.info("找到已有追踪文件夹「%s」: %s",
                                    self.TRACKING_FOLDER_NAME, self._tracking_folder_token)
                        return self._tracking_folder_token

            # 创建
            logger.info("追踪文件夹「%s」不存在，正在创建...", self.TRACKING_FOLDER_NAME)
            r2 = requests.post(
                "https://open.feishu.cn/open-apis/drive/v1/files/create_folder",
                headers=headers,
                json={"name": self.TRACKING_FOLDER_NAME, "folder_token": parent_token},
                timeout=10,
            )
            if r2.status_code == 200 and r2.json().get("code") == 0:
                self._tracking_folder_token = r2.json()["data"]["token"]
                logger.info("追踪文件夹创建成功: %s", self._tracking_folder_token)
                return self._tracking_folder_token
            else:
                logger.error("创建追踪文件夹失败: %s", r2.text[:300])
                return None

        except Exception as e:
            logger.error("追踪文件夹异常: %s", e)
            return None

    def find_tracking_doc(self, folder_token: str,
                          stock_code: str) -> Optional[dict]:
        """在追踪文件夹中按文件名前缀查找已有文档

        Returns:
            {"token": str, "url": str} 或 None
        """
        headers = self._rest_headers()
        if not headers.get("Authorization"):
            return None

        prefix = f"{stock_code.upper()} "
        try:
            r = requests.get(
                "https://open.feishu.cn/open-apis/drive/v1/files",
                headers={"Authorization": headers["Authorization"]},
                params={"folder_token": folder_token, "page_size": 100},
                timeout=10,
            )
            if r.status_code != 200:
                return None

            for f in r.json().get("data", {}).get("files", []):
                name = f.get("name", "")
                if f.get("type") == "docx" and name.startswith(prefix):
                    doc_token = f["token"]
                    return {
                        "token": doc_token,
                        "url": f"https://feishu.cn/docx/{doc_token}",
                    }
            return None

        except Exception as e:
            logger.error("查找追踪文档失败: %s", e)
            return None

    def create_tracking_doc(self, folder_token: str, stock_code: str,
                            stock_name: str) -> Optional[dict]:
        """创建追踪文档

        标题格式: "600519 贵州茅台 — 分析追踪"

        Returns:
            {"token": str, "url": str} 或 None
        """
        if not self.client or not self.is_configured():
            return None

        title = f"{stock_code.upper()} {stock_name} — 分析追踪"

        try:
            body = CreateDocumentRequestBody.builder() \
                .title(title) \
                .folder_token(folder_token) \
                .build()

            req = CreateDocumentRequest.builder() \
                .request_body(body) \
                .build()

            resp = self.client.docx.v1.document.create(req)
            if not resp.success():
                logger.error("创建追踪文档失败: %s - %s", resp.code, resp.msg)
                return None

            doc_token = resp.data.document.document_id
            doc_url = f"https://feishu.cn/docx/{doc_token}"
            logger.info("追踪文档创建成功: %s (ID: %s)", title, doc_token)

            # 添加文档主标题
            header_block = Block.builder() \
                .block_type(3) \
                .heading1(Text.builder()
                          .elements([TextElement.builder()
                                    .text_run(TextRun.builder()
                                              .content(title)
                                              .text_element_style(TextElementStyle.builder().build())
                                              .build())
                                    .build()])
                          .style(TextStyle.builder().build())
                          .build()) \
                .build()

            add_req = CreateDocumentBlockChildrenRequest.builder() \
                .document_id(doc_token) \
                .block_id(doc_token) \
                .request_body(CreateDocumentBlockChildrenRequestBody.builder()
                              .children([header_block])
                              .index(-1)
                              .build()) \
                .build()

            self.client.docx.v1.document_block_children.create(add_req)

            return {"token": doc_token, "url": doc_url}

        except Exception as e:
            logger.error("创建追踪文档异常: %s", e)
            return None

    def append_analysis_block(self, doc_token: str,
                              markdown_block: str) -> bool:
        """向追踪文档末尾追加一个分析块（分隔线 + Markdown 内容）"""
        if not self.client or not self.is_configured():
            return False

        try:
            # 添加分隔线
            divider_block = Block.builder() \
                .block_type(22) \
                .divider(Divider.builder().build()) \
                .build()

            add_div_req = CreateDocumentBlockChildrenRequest.builder() \
                .document_id(doc_token) \
                .block_id(doc_token) \
                .request_body(CreateDocumentBlockChildrenRequestBody.builder()
                              .children([divider_block])
                              .index(-1)
                              .build()) \
                .build()

            self.client.docx.v1.document_block_children.create(add_div_req)

            # 转换并添加内容块
            blocks = self._markdown_to_sdk_blocks(markdown_block)
            batch_size = 50
            for i in range(0, len(blocks), batch_size):
                batch_blocks = blocks[i:i + batch_size]
                add_req = CreateDocumentBlockChildrenRequest.builder() \
                    .document_id(doc_token) \
                    .block_id(doc_token) \
                    .request_body(CreateDocumentBlockChildrenRequestBody.builder()
                                  .children(batch_blocks)
                                  .index(-1)
                                  .build()) \
                    .build()
                resp = self.client.docx.v1.document_block_children.create(add_req)
                if not resp.success():
                    logger.error("追加追踪文档块失败(批次%d): %s - %s",
                                 i, resp.code, resp.msg)
                    return False

            logger.info("追踪文档分析块追加成功: %s", doc_token)
            return True

        except Exception as e:
            logger.error("追加追踪文档异常: %s", e)
            return False

    def _markdown_to_sdk_blocks(self, md_text: str) -> List[Block]:
        """将简单 Markdown 转换为飞书 SDK Block 对象"""
        blocks = []
        lines = md_text.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            block_type = 2  # 默认普通文本
            text_content = line

            if line.startswith("# "):
                block_type = 3
                text_content = line[2:]
            elif line.startswith("## "):
                block_type = 4
                text_content = line[3:]
            elif line.startswith("### "):
                block_type = 5
                text_content = line[4:]
            elif line.startswith("---"):
                blocks.append(Block.builder()
                              .block_type(22)
                              .divider(Divider.builder().build())
                              .build())
                continue

            text_run = TextRun.builder() \
                .content(text_content) \
                .text_element_style(TextElementStyle.builder().build()) \
                .build()

            text_element = TextElement.builder() \
                .text_run(text_run) \
                .build()

            text_obj = Text.builder() \
                .elements([text_element]) \
                .style(TextStyle.builder().build()) \
                .build()

            block_builder = Block.builder().block_type(block_type)

            if block_type == 2:
                block_builder.text(text_obj)
            elif block_type == 3:
                block_builder.heading1(text_obj)
            elif block_type == 4:
                block_builder.heading2(text_obj)
            elif block_type == 5:
                block_builder.heading3(text_obj)

            blocks.append(block_builder.build())

        return blocks
