import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import socket
import ssl
import time
import re
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
        
        # 在新线程中发送请求
        thread = threading.Thread(target=self._send_requests_thread, args=(req1_text, req2_text))
        thread.daemon = True
        thread.start()
    
    def _send_requests_thread(self, req1_text, req2_text):
        """在新线程中发送请求"""
        start_time = time.time()
        
        # 清空之前的结果
        self.response1_results = []
        self.response2_results = []
        
        # 获取延迟时间和并发次数
        try:
            delay_ms = int(self.delay_var.get())
        except ValueError:
            delay_ms = 0
            
        try:
            concurrent_count = int(self.concurrent_var.get())
        except ValueError:
            concurrent_count = 1
        
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
                        args=(1, req1_text, delay_ms, i, concurrent_count, barrier)
                    )
                    threads.append(thread1)
                if req2_text:
                    thread2 = threading.Thread(
                        target=self._send_single_request, 
                        args=(2, req2_text, delay_ms, i, concurrent_count, barrier)
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
        """规范化HTTP请求的换行符为CRLF"""
        if not text:
            return text
        # 先统一为\n，再转换为\r\n
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = text.replace('\n', '\r\n')
        # 确保请求以\r\n\r\n结尾（如果有body的话）
        if not text.endswith('\r\n'):
            text += '\r\n'
        return text
    
    def _send_single_request(self, req_num, request_text, delay_ms=0, request_id=0, concurrent_count=1, barrier=None):
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
            host, port, is_https = self._parse_request_target(request_text)
            
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
            error_entry = {
                'id': request_id + 1,
                'time': 0,
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
    
    def _parse_request_target(self, request_text):
        """从请求包中解析目标主机和端口"""
        lines = request_text.split('\r\n') if '\r\n' in request_text else request_text.split('\n')
        host = None
        port = 80
        is_https = self.https_var.get()  # 检查强制HTTPS选项
        
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
            if not request_text.endswith('\r\n\r\n'):
                if '\r\n\r\n' not in request_text:
                    # 没有空行分隔header和body，添加一个
                    request_text += '\r\n'
            
            sock.sendall(request_text.encode('utf-8'))

            
            # 接收完整的HTTP响应
            response = self._receive_complete_response(sock)

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
                    # 关闭当前连接
                    sock.close()
                    
                    # 解析重定向位置
                    new_host, new_port, new_is_https = self._parse_redirect_location(location, host, port)
                    
                    # 递归调用处理重定向
                    return self._send_raw_http(
                        request_text, new_host, new_port, new_is_https, max_redirects - 1
                    )
        finally:
            sock.close()

        return response.decode('utf-8', errors='replace')
    
    def _receive_complete_response(self, sock):
        """接收完整的HTTP响应，支持Content-Length和分块传输"""
        response = b""
        headers_complete = False
        content_length = None
        is_chunked = False
        body_start = 0
        
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
        
        # 第二阶段：根据头部信息接收响应体
        if content_length is not None:
            # 使用Content-Length确定响应体长度
            body_received = len(response) - body_start
            while body_received < content_length:
                data = sock.recv(4096)
                if not data:
                    break
                response += data
                body_received += len(data)
                
        elif is_chunked:
            # 处理分块传输编码
            response = self._receive_chunked_response(sock, response, body_start)
            
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
        """处理分块传输编码的响应"""
        response = current_response
        chunk_data = response[body_start:]
        
        while True:
            # 查找块大小行
            chunk_size_line_end = chunk_data.find(b"\r\n")
            if chunk_size_line_end == -1:
                # 需要更多数据来获取块大小
                data = sock.recv(4096)
                if not data:
                    break
                chunk_data += data
                continue
            
            chunk_size_line = chunk_data[:chunk_size_line_end]
            try:
                # 解析16进制块大小
                chunk_size = int(chunk_size_line, 16)
            except ValueError:
                # 无效的块大小，可能遇到结束块
                if chunk_size_line == b"0":
                    break
                # 其他情况，按普通数据处理
                chunk_data = chunk_data[chunk_size_line_end + 2:]
                continue
            
            if chunk_size == 0:
                # 结束块
                break
            
            # 计算当前已接收的块数据
            chunk_start = chunk_size_line_end + 2
            chunk_end = chunk_start + chunk_size
            chunk_trailer = chunk_end + 2  # 包括\r\n
            
            # 如果当前数据不够完整块，继续接收
            while len(chunk_data) < chunk_trailer:
                data = sock.recv(4096)
                if not data:
                    break
                chunk_data += data
            
            if len(chunk_data) >= chunk_trailer:
                # 提取完整的块数据
                chunk = chunk_data[chunk_start:chunk_end]
                response += chunk
                # 移动到下一个块
                chunk_data = chunk_data[chunk_trailer:]
            else:
                # 数据不完整，退出
                break
        
        return response
    
    def _extract_location_header(self, response):
        """从HTTP响应中提取Location头部"""
        headers_part = response.split(b'\r\n\r\n')[0]
        for line in headers_part.split(b'\r\n'):
            if line.lower().startswith(b'location:'):
                return line.split(b':', 1)[1].strip().decode('utf-8')
        return None

    def _parse_redirect_location(self, location_url, original_host, original_port):
        """解析重定向URL"""
        try:
            parsed = urlparse(location_url)
            host = parsed.hostname or original_host
            port = parsed.port or (443 if parsed.scheme == 'https' else 80)
            is_https = parsed.scheme == 'https'
            return host, port, is_https
        except Exception:
            return original_host, original_port, False
            
    def _update_response_ui(self, text_widget, response, elapsed_time=0, request_id=0):
        """更新响应UI"""
        # 不清空文本，而是追加内容（用于并发显示）
        if request_id == 0:
            text_widget.delete(1.0, tk.END)
        
        if elapsed_time > 0:
            text_widget.insert(tk.END, f"[请求{request_id+1}] 响应时间: {elapsed_time:.0f} ms\n")
        
        text_widget.insert(tk.END, response)
        text_widget.insert(tk.END, "\n" + "="*50 + "\n\n")
    
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
            times = [r['time'] for r in self.response1_results]
            
            report += f"  总请求数: {len(self.response1_results)}\n"
            report += f"  状态码分布: {dict((s, statuses.count(s)) for s in set(statuses))}\n"
            report += f"  响应时间: 最小={min(times):.0f}ms, 最大={max(times):.0f}ms, 平均={sum(times)/len(times):.0f}ms\n"
            
            # 检测响应内容差异
            unique_responses = len(set(r['response'][:500] for r in self.response1_results))
            if unique_responses > 1:
                report += f"  ⚠️ 发现 {unique_responses} 种不同响应内容！可能存在竞态条件\n"
            report += "\n"
        
        # 分析响应2
        if self.response2_results:
            report += "【请求包2 响应分析】\n"
            statuses = [r['status'] for r in self.response2_results]
            times = [r['time'] for r in self.response2_results]
            
            report += f"  总请求数: {len(self.response2_results)}\n"
            report += f"  状态码分布: {dict((s, statuses.count(s)) for s in set(statuses))}\n"
            report += f"  响应时间: 最小={min(times):.0f}ms, 最大={max(times):.0f}ms, 平均={sum(times)/len(times):.0f}ms\n"
            
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
