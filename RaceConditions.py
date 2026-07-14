import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import socket
import ssl
import time
import re
import gzip
import zlib
from urllib.parse import urlparse

class RawHTTPRepeater:
    def __init__(self, root):
        self.root = root
        self.root.title("HTTP原始数据包并发发送工具 (竞态条件测试)")
        self.root.geometry("1100x750")
        
        # 创建主框架
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建请求面板
        self.create_request_panel(main_frame)
        
        # 创建响应面板
        self.create_response_panel(main_frame)
        
        # 状态栏
        self.status_bar = ttk.Label(main_frame, text="就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 响应锁（用于线程安全更新UI）
        self.response_lock = threading.Lock()
        self.response1_results = []
        self.response2_results = []


    def create_request_panel(self, parent):
            # 请求面板容器
            request_frame = ttk.LabelFrame(parent, text="原始HTTP请求包", padding="10")
            request_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
            
            # 创建两个请求面板
            paned_window = ttk.PanedWindow(request_frame, orient=tk.HORIZONTAL)
            paned_window.pack(fill=tk.BOTH, expand=True)
            
            # 请求1面板
            req1_frame = ttk.Frame(paned_window)
            paned_window.add(req1_frame, weight=1)
            
            ttk.Label(req1_frame, text="请求包 1:").pack(anchor=tk.W)
            self.request1 = scrolledtext.ScrolledText(req1_frame, height=12, width=50)
            self.request1.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
            
            # 请求2面板
            req2_frame = ttk.Frame(paned_window)
            paned_window.add(req2_frame, weight=1)
            
            ttk.Label(req2_frame, text="请求包 2:").pack(anchor=tk.W)
            self.request2 = scrolledtext.ScrolledText(req2_frame, height=12, width=50)
            self.request2.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
            
            # 控制按钮和延迟设置
            control_frame = ttk.Frame(request_frame)
            control_frame.pack(fill=tk.X, pady=(10, 0))
            
            # 按钮区域
            button_frame = ttk.Frame(control_frame)
            button_frame.pack(side=tk.LEFT)
            
            ttk.Button(button_frame, text="同时发送请求", command=self.send_requests).pack(side=tk.LEFT, padx=(0, 10))
            ttk.Button(button_frame, text="清空所有", command=self.clear_all).pack(side=tk.LEFT, padx=(0, 10))
            ttk.Button(button_frame, text="解析请求", command=self.parse_requests).pack(side=tk.LEFT, padx=(0, 10))
            ttk.Button(button_frame, text="对比响应", command=self.compare_responses).pack(side=tk.LEFT)
            
            # 设置区域（右侧）
            settings_frame = ttk.Frame(control_frame)
            settings_frame.pack(side=tk.RIGHT)
            
            # HTTPS选项
            self.https_var = tk.BooleanVar(value=False)
            ttk.Checkbutton(settings_frame, text="强制HTTPS", variable=self.https_var).pack(side=tk.LEFT, padx=(0, 15))
            
            # 并发设置
            ttk.Label(settings_frame, text="并发次数:").pack(side=tk.LEFT, padx=(0, 5))
            self.concurrent_var = tk.StringVar(value="1")
            concurrent_spin = ttk.Spinbox(settings_frame, from_=1, to=100, textvariable=self.concurrent_var, width=6)
            concurrent_spin.pack(side=tk.LEFT, padx=(0, 15))
            
            # 延迟设置
            ttk.Label(settings_frame, text="请求延迟(ms):").pack(side=tk.LEFT, padx=(0, 5))
            self.delay_var = tk.StringVar(value="0")
            delay_spin = ttk.Spinbox(settings_frame, from_=0, to=10000, textvariable=self.delay_var, width=8)
            delay_spin.pack(side=tk.LEFT)
    
    def create_response_panel(self, parent):
        # 响应面板容器
        response_frame = ttk.LabelFrame(parent, text="响应结果", padding="10")
        response_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建两个响应面板
        paned_window = ttk.PanedWindow(response_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)
        
        # 响应1面板
        resp1_frame = ttk.Frame(paned_window)
        paned_window.add(resp1_frame, weight=1)
        
        ttk.Label(resp1_frame, text="响应 1:").pack(anchor=tk.W)
        self.response1 = scrolledtext.ScrolledText(resp1_frame, height=12, width=50)
        self.response1.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        # 响应2面板
        resp2_frame = ttk.Frame(paned_window)
        paned_window.add(resp2_frame, weight=1)
        
        ttk.Label(resp2_frame, text="响应 2:").pack(anchor=tk.W)
        self.response2 = scrolledtext.ScrolledText(resp2_frame, height=12, width=50)
        self.response2.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
    
    def send_requests(self):
        """发送原始HTTP请求（支持单个或两个请求包）"""
        self.status_bar.config(text="正在发送请求...")
        
        # 获取请求包内容
        req1_text = self.request1.get(1.0, tk.END).strip()
        req2_text = self.request2.get(1.0, tk.END).strip()
        
        # 验证请求包
        if not req1_text and not req2_text:
            messagebox.showerror("错误", "至少需要一个请求包")
            self.status_bar.config(text="错误: 至少需要一个请求包")
            return

        # 在主线程采集配置（tkinter 变量非线程安全，不能在工作线程中读取）
        try:
            delay_ms = int(self.delay_var.get())
        except ValueError:
            delay_ms = 0
        try:
            concurrent_count = int(self.concurrent_var.get())
        except ValueError:
            concurrent_count = 1
        concurrent_count = max(1, concurrent_count)  # 防止 Barrier(0) 崩溃
        force_https = self.https_var.get()

        # 在新线程中发送请求
        thread = threading.Thread(
            target=self._send_requests_thread,
            args=(req1_text, req2_text, delay_ms, concurrent_count, force_https)
        )
        thread.daemon = True
        thread.start()
    
    def _send_requests_thread(self, req1_text, req2_text, delay_ms=0, concurrent_count=1, force_https=False):
        """在新线程中发送请求"""
        start_time = time.time()

        # 清空之前的结果
        self.response1_results = []
        self.response2_results = []

        # 规范化请求包换行符
        req1_text = self._normalize_line_endings(req1_text)
        req2_text = self._normalize_line_endings(req2_text)
        
        # 清空响应区域
        self.root.after(0, lambda: self.response1.delete(1.0, tk.END))
        self.root.after(0, lambda: self.response2.delete(1.0, tk.END))
        
        # 发送请求
        try:
            threads = []
            barrier = threading.Barrier(
                (1 if req1_text else 0) * concurrent_count + 
                (1 if req2_text else 0) * concurrent_count
            )
            
            # 创建并发线程
            for i in range(concurrent_count):
                if req1_text:
                    thread1 = threading.Thread(
                        target=self._send_single_request,
                        args=(1, req1_text, delay_ms, i, concurrent_count, barrier, force_https)
                    )
                    threads.append(thread1)
                if req2_text:
                    thread2 = threading.Thread(
                        target=self._send_single_request,
                        args=(2, req2_text, delay_ms, i, concurrent_count, barrier, force_https)
                    )
                    threads.append(thread2)
            
            # 启动所有线程
            for thread in threads:
                thread.start()
            
            # 等待所有线程完成
            for thread in threads:
                thread.join()
            
            elapsed_time = time.time() - start_time
            self.root.after(0, lambda: self.status_bar.config(
                text=f"请求完成 (总耗时: {elapsed_time:.2f}秒, 并发: {concurrent_count}次)"
            ))
            
        except Exception as e:
            self.root.after(0, lambda: self.status_bar.config(text=f"错误: {str(e)}"))
    
    def _normalize_line_endings(self, text):
        """规范化HTTP请求头部换行符为CRLF（不改动 body，避免破坏二进制数据）"""
        if not text:
            return text
        # 分离 header 与 body（首个空行）
        if '\r\n\r\n' in text:
            pos = text.find('\r\n\r\n')
            headers, body, sep = text[:pos], text[pos + 4:], '\r\n\r\n'
        elif '\n\n' in text:
            pos = text.find('\n\n')
            headers, body, sep = text[:pos], text[pos + 2:], '\r\n\r\n'
        else:
            headers, body, sep = text, None, ''
        # 仅规范化 header 部分的换行符
        headers = headers.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\r\n')
        if body is not None:
            return headers + sep + body
        # 只有 header，补一个 CRLF 结尾
        if not headers.endswith('\r\n'):
            headers += '\r\n'
        return headers
    
    def _send_single_request(self, req_num, request_text, delay_ms=0, request_id=0, concurrent_count=1, barrier=None, force_https=False):
        """发送单个原始HTTP请求"""
        # 等待所有线程就绪后同时发送（真正的并发）
        if barrier:
            try:
                barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                pass

        # 应用请求延迟
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)

        start_time = time.time()

        try:
            # 解析请求包获取目标主机和端口
            host, port, is_https = self._parse_request_target(request_text, force_https)
            
            # 发送原始HTTP请求
            response = self._send_raw_http(request_text, host, port, is_https, max_redirects=5)
            elapsed_time = (time.time() - start_time) * 1000  # 转换为毫秒
            
            # 更新UI（线程安全）
            with self.response_lock:
                result_entry = {
                    'id': request_id + 1,
                    'time': elapsed_time,
                    'response': response,
                    'status': self._extract_status_code(response)
                }
                
                if req_num == 1:
                    self.response1_results.append(result_entry)
                    self.root.after(0, lambda r=result_entry: self._append_response(self.response1, r))
                else:
                    self.response2_results.append(result_entry)
                    self.root.after(0, lambda r=result_entry: self._append_response(self.response2, r))
                
        except Exception as e:
            elapsed_time = (time.time() - start_time) * 1000
            error_entry = {
                'id': request_id + 1,
                'time': elapsed_time,
                'response': f"请求失败: {str(e)}",
                'status': 'ERROR'
            }
            with self.response_lock:
                if req_num == 1:
                    self.response1_results.append(error_entry)
                    self.root.after(0, lambda r=error_entry: self._append_response(self.response1, r))
                else:
                    self.response2_results.append(error_entry)
                    self.root.after(0, lambda r=error_entry: self._append_response(self.response2, r))

    def _extract_status_code(self, response):
        """从响应中提取状态码"""
        try:
            first_line = response.split('\r\n')[0] if '\r\n' in response else response.split('\n')[0]
            parts = first_line.split(' ')
            if len(parts) >= 2:
                return parts[1]
        except:
            pass
        return 'UNKNOWN'
    
    def _append_response(self, text_widget, result):
        """追加响应到文本框"""
        text_widget.insert(tk.END, f"{'='*50}\n")
        text_widget.insert(tk.END, f"[请求 #{result['id']}] 状态: {result['status']} | 耗时: {result['time']:.0f}ms\n")
        text_widget.insert(tk.END, f"{'='*50}\n")
        text_widget.insert(tk.END, result['response'])
        text_widget.insert(tk.END, "\n\n")
        text_widget.see(tk.END)
    
    def _parse_request_target(self, request_text, force_https=False):
        """从请求包中解析目标主机和端口"""
        lines = request_text.split('\r\n') if '\r\n' in request_text else request_text.split('\n')
        host = None
        port = 80
        is_https = force_https  # 是否强制 HTTPS（由主线程传入，避免工作线程读取 tkinter 变量）
        
        # 检查请求行
        first_line = lines[0].strip()
        if first_line.startswith(('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS')):
            # 解析Host头
            for line in lines[1:]:
                if line.strip() == '':
                    break  # 空行表示头部结束
                if line.lower().startswith('host:'):
                    host_part = line[5:].strip()
                    if ':' in host_part:
                        host, port_str = host_part.rsplit(':', 1)
                        try:
                            port = int(port_str)
                        except ValueError:
                            port = 443 if is_https else 80
                    else:
                        host = host_part
                    break
            
            # 如果没有找到Host头，尝试从请求行中提取
            if not host:
                parts = first_line.split(' ')
                if len(parts) >= 2:
                    url_part = parts[1]
                    if url_part.startswith('http'):
                        parsed = urlparse(url_part)
                        host = parsed.hostname
                        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
                        is_https = parsed.scheme == 'https'
        
        if not host:
            raise ValueError("无法从请求包中解析目标主机，请检查Host头")
        
        # 根据端口自动判断HTTPS
        if port == 443:
            is_https = True
        
        # 如果强制HTTPS且端口是80，改为443
        if is_https and port == 80:
            port = 443
        
        return host, port, is_https
    
    def _send_raw_http(self, request_text, host, port, is_https, max_redirects=5):
        """发送原始HTTP请求"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        
        try:
            sock.connect((host, port))
            
            if is_https:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE  # 忽略证书验证（测试用）
                sock = context.wrap_socket(sock, server_hostname=host)
            
            # 确保请求以正确的换行符结尾
            if '\r\n\r\n' in request_text:
                # 已有 header/body 分隔，保证 body 以 CRLF 结尾
                if not request_text.endswith('\r\n'):
                    request_text += '\r\n'
            else:
                # 仅有 header，补上结束空行
                request_text += '\r\n\r\n'

            sock.sendall(request_text.encode('utf-8'))

            # 解析请求方法（用于判断响应是否含 body）
            method = request_text.split(' ', 1)[0].upper() if request_text else 'GET'

            # 接收完整的HTTP响应
            response = self._receive_complete_response(sock, method)

            # 检查重定向
            status_line = response.split(b'\r\n')[0]
            try:
                status_code = int(status_line.split(b' ')[1])
            except (IndexError, ValueError):
                status_code = 200

            # 如果是重定向且还有重定向次数
            if status_code in [301, 302, 303, 307, 308] and max_redirects > 0:
                location = self._extract_location_header(response)
                if location:
                    # 解析重定向位置（相对路径回退到原始连接参数）
                    new_host, new_port, new_is_https = self._parse_redirect_location(
                        location, host, port, is_https
                    )
                    # 目标主机变化时重写 Host 头以匹配新目标
                    new_request_text = self._rewrite_host_header(
                        request_text, new_host, new_port, new_is_https
                    )
                    # 依赖 finally 关闭当前 socket，递归处理重定向
                    return self._send_raw_http(
                        new_request_text, new_host, new_port, new_is_https, max_redirects - 1
                    )
        finally:
            sock.close()

        return self._decode_response(response)
    
    def _receive_complete_response(self, sock, method="GET"):
        """接收完整的HTTP响应，支持Content-Length和分块传输"""
        response = b""
        headers_complete = False
        content_length = None
        is_chunked = False
        body_start = 0
        status_code = None

        # 第一阶段：接收响应头
        while not headers_complete:
            data = sock.recv(4096)
            if not data:
                break
            response += data

            # 检查是否收到完整的头部（空行\r\n\r\n）
            header_end_pos = response.find(b"\r\n\r\n")
            if header_end_pos != -1:
                headers_complete = True
                headers = response[:header_end_pos]
                body_start = header_end_pos + 4

                # 解析状态码
                try:
                    status_line = headers.split(b"\r\n")[0]
                    status_code = int(status_line.split(b" ")[1])
                except (IndexError, ValueError):
                    status_code = None

                # 解析头部信息
                for line in headers.split(b"\r\n"):
                    line_lower = line.lower()
                    if line_lower.startswith(b"content-length:"):
                        try:
                            content_length = int(line.split(b":")[1].strip())
                        except (ValueError, IndexError):
                            pass

                    if line_lower.startswith(b"transfer-encoding:") and b"chunked" in line_lower:
                        is_chunked = True

        # 这些情况响应体为空：HEAD 请求 / 204 / 304 / 1xx
        no_body = (
            method.upper() == "HEAD"
            or status_code in (204, 304)
            or (status_code is not None and 100 <= status_code < 200)
        )
        if no_body:
            return response[:body_start]

        # 第二阶段：根据头部信息接收响应体
        # 注意：同时存在 Transfer-Encoding: chunked 与 Content-Length 时，按规范优先 chunked
        if is_chunked:
            # 处理分块传输编码
            response = self._receive_chunked_response(sock, response, body_start)

        elif content_length is not None:
            # 使用Content-Length确定响应体长度
            body_received = len(response) - body_start
            while body_received < content_length:
                data = sock.recv(4096)
                if not data:
                    break
                response += data
                body_received += len(data)

        else:
            # 没有Content-Length也不是分块传输，接收直到连接关闭或超时
            try:
                while True:
                    data = sock.recv(4096)
                    if not data:
                        break
                    response += data
            except socket.timeout:
                pass

        return response
    
    def _receive_chunked_response(self, sock, current_response, body_start):
        """处理分块传输编码的响应，返回 headers + 解码后的 body"""
        headers_part = current_response[:body_start]  # 含 header 与 \r\n\r\n 分隔符
        chunk_data = current_response[body_start:]    # 原始 chunked 字节
        decoded_body = b""

        while True:
            # 确保至少有一行（块大小行以 \r\n 结尾）
            while b"\r\n" not in chunk_data:
                data = sock.recv(4096)
                if not data:
                    return headers_part + decoded_body + chunk_data
                chunk_data += data

            # 解析块大小行（忽略 chunk 扩展，如 ";name=value"）
            size_line_end = chunk_data.find(b"\r\n")
            size_token = chunk_data[:size_line_end].split(b";")[0].strip()
            try:
                chunk_size = int(size_token, 16)
            except ValueError:
                # 无法解析的块大小，原样附加剩余数据后返回
                return headers_part + decoded_body + chunk_data

            # 跳过块大小行
            chunk_data = chunk_data[size_line_end + 2:]

            if chunk_size == 0:
                # 结束块，忽略可能的 trailer，直接结束
                break

            # 确保本块数据 + 结尾 \r\n 完整
            while len(chunk_data) < chunk_size + 2:
                data = sock.recv(4096)
                if not data:
                    break
                chunk_data += data

            decoded_body += chunk_data[:chunk_size]
            chunk_data = chunk_data[chunk_size + 2:]  # 跳过块数据与结尾 \r\n

        return headers_part + decoded_body
    
    def _decode_response(self, response):
        """对完整响应做解压 + 字符集解码，避免乱码"""
        sep = response.find(b'\r\n\r\n')
        if sep == -1:
            return response.decode('utf-8', errors='replace')

        headers_bytes = response[:sep]
        body_bytes = response[sep + 4:]
        header_lines = headers_bytes.split(b'\r\n')

        # 1) 按 Content-Encoding 解压响应体
        content_encoding = None
        for line in header_lines:
            if line.lower().startswith(b'content-encoding:'):
                content_encoding = line.split(b':', 1)[1].strip()
                break
        body_bytes = self._decompress_body(body_bytes, content_encoding)

        # 2) 探测字符集
        charset = self._detect_charset(header_lines, body_bytes)

        # header 用 latin-1（ASCII 兼容且安全），body 用探测到的字符集
        headers_text = headers_bytes.decode('latin-1', errors='replace')
        try:
            body_text = body_bytes.decode(charset, errors='replace')
        except (LookupError, TypeError):
            body_text = body_bytes.decode('utf-8', errors='replace')

        return headers_text + '\r\n\r\n' + body_text

    def _decompress_body(self, body, content_encoding):
        """按 Content-Encoding 解压响应体"""
        if not body or not content_encoding:
            return body
        encoding = content_encoding.decode('latin-1', errors='replace').lower()
        try:
            if 'gzip' in encoding:
                return gzip.decompress(body)
            if 'deflate' in encoding:
                try:
                    return zlib.decompress(body)
                except zlib.error:
                    # 部分服务器发送的是裸 deflate 流（无 zlib 头）
                    return zlib.decompress(body, -zlib.MAX_WBITS)
            if 'br' in encoding:
                try:
                    import brotli
                    return brotli.decompress(body)
                except ImportError:
                    return body  # 未安装 brotli，原样返回（显示会乱码但不崩溃）
        except Exception:
            return body
        return body

    def _detect_charset(self, header_lines, body):
        """探测字符集：Content-Type 的 charset → HTML meta → 回退 utf-8"""
        # 1) Content-Type 头中的 charset
        for line in header_lines:
            if line.lower().startswith(b'content-type:'):
                for token in line.split(b';'):
                    token = token.strip().lower()
                    if token.startswith(b'charset='):
                        charset = token.split(b'=', 1)[1].strip().strip(b'"\'')
                        charset = charset.decode('ascii', errors='ignore')
                        if charset:
                            return charset
                break
        # 2) HTML meta 中的 charset（只看前 4KB）
        if body:
            m = re.search(rb'charset\s*=\s*["\']?\s*([A-Za-z0-9_\-]+)', body[:4096], re.IGNORECASE)
            if m:
                return m.group(1).decode('ascii', errors='ignore')
        return 'utf-8'

    def _extract_location_header(self, response):
        """从HTTP响应中提取Location头部"""
        headers_part = response.split(b'\r\n\r\n')[0]
        for line in headers_part.split(b'\r\n'):
            if line.lower().startswith(b'location:'):
                return line.split(b':', 1)[1].strip().decode('latin-1', errors='replace')
        return None

    def _parse_redirect_location(self, location_url, original_host, original_port, original_is_https):
        """解析重定向URL。绝对URL按其自身scheme/port；相对路径回退到原始连接参数"""
        try:
            parsed = urlparse(location_url)
            host = parsed.hostname
            if host:
                # 绝对 URL
                if parsed.scheme in ('http', 'https'):
                    is_https = parsed.scheme == 'https'
                else:
                    is_https = original_is_https
                port = parsed.port or (443 if is_https else 80)
                return host, port, is_https
            else:
                # 相对路径，沿用原始 host/port/协议
                return original_host, original_port, original_is_https
        except Exception:
            return original_host, original_port, original_is_https
            
    def _rewrite_host_header(self, request_text, host, port, is_https):
        """重写请求中的 Host 头以匹配重定向目标"""
        # 默认端口(80/http、443/https)省略，其余带上端口
        default_port = 443 if is_https else 80
        host_value = host if port == default_port else f"{host}:{port}"
        lines = request_text.split('\r\n')
        for idx, line in enumerate(lines):
            if line.lower().startswith('host:'):
                lines[idx] = f'Host: {host_value}'
                break
        return '\r\n'.join(lines)

    def clear_all(self):
        """清空所有内容"""
        self.request1.delete(1.0, tk.END)
        self.request2.delete(1.0, tk.END)
        self.response1.delete(1.0, tk.END)
        self.response2.delete(1.0, tk.END)
        self.response1_results = []
        self.response2_results = []
        self.status_bar.config(text="已清空所有内容")
    
    def compare_responses(self):
        """对比响应结果（用于检测竞态条件）"""
        if not self.response1_results and not self.response2_results:
            messagebox.showinfo("对比结果", "没有响应数据可对比")
            return
        
        report = "=== 响应对比分析 ===\n\n"
        
        # 分析响应1
        if self.response1_results:
            report += "【请求包1 响应分析】\n"
            statuses = [r['status'] for r in self.response1_results]
            # 统计响应时间时排除失败请求（status == 'ERROR'）
            times = [r['time'] for r in self.response1_results if r['status'] != 'ERROR']

            report += f"  总请求数: {len(self.response1_results)}\n"
            report += f"  状态码分布: {dict((s, statuses.count(s)) for s in set(statuses))}\n"
            if times:
                report += f"  响应时间: 最小={min(times):.0f}ms, 最大={max(times):.0f}ms, 平均={sum(times)/len(times):.0f}ms\n"
            else:
                report += f"  响应时间: 无成功请求\n"

            # 检测响应内容差异
            unique_responses = len(set(r['response'][:500] for r in self.response1_results))
            if unique_responses > 1:
                report += f"  ⚠️ 发现 {unique_responses} 种不同响应内容！可能存在竞态条件\n"
            report += "\n"
        
        # 分析响应2
        if self.response2_results:
            report += "【请求包2 响应分析】\n"
            statuses = [r['status'] for r in self.response2_results]
            times = [r['time'] for r in self.response2_results if r['status'] != 'ERROR']

            report += f"  总请求数: {len(self.response2_results)}\n"
            report += f"  状态码分布: {dict((s, statuses.count(s)) for s in set(statuses))}\n"
            if times:
                report += f"  响应时间: 最小={min(times):.0f}ms, 最大={max(times):.0f}ms, 平均={sum(times)/len(times):.0f}ms\n"
            else:
                report += f"  响应时间: 无成功请求\n"

            unique_responses = len(set(r['response'][:500] for r in self.response2_results))
            if unique_responses > 1:
                report += f"  ⚠️ 发现 {unique_responses} 种不同响应内容！可能存在竞态条件\n"
        
        messagebox.showinfo("响应对比分析", report)
    
    def parse_requests(self):
        """解析请求包并显示信息"""
        try:
            req1_text = self.request1.get(1.0, tk.END).strip()
            req2_text = self.request2.get(1.0, tk.END).strip()
            
            info1 = self._parse_request_info(req1_text)
            info2 = self._parse_request_info(req2_text)
            
            message = f"请求1:\n{info1}\n\n请求2:\n{info2}"
            messagebox.showinfo("请求解析", message)
            
        except Exception as e:
            messagebox.showerror("解析错误", f"解析请求时出错: {str(e)}")
    
    def _parse_request_info(self, request_text):
        """解析请求包信息"""
        lines = request_text.split('\n')
        if not lines:
            return "空请求"
        
        # 解析请求行
        first_line = lines[0].strip()
        parts = first_line.split(' ')
        method = parts[0] if parts else "UNKNOWN"
        path = parts[1] if len(parts) > 1 else "UNKNOWN"
        version = parts[2] if len(parts) > 2 else "UNKNOWN"
        
        # 解析头部
        headers = {}
        body_start = False
        for line in lines[1:]:
            if line.strip() == '':
                body_start = True
                continue
            if not body_start and ':' in line:
                key, value = line.split(':', 1)
                headers[key.strip()] = value.strip()
        
        # 获取Host
        host = headers.get('Host', '未知')
        
        # 获取Content-Length
        content_length = headers.get('Content-Length', '未知')
        
        # 获取Content-Type
        content_type = headers.get('Content-Type', '未知')
        
        return f"方法: {method}\n路径: {path}\n主机: {host}\n内容类型: {content_type}\n内容长度: {content_length}"

if __name__ == "__main__":
    root = tk.Tk()
    app = RawHTTPRepeater(root)
    root.mainloop()
