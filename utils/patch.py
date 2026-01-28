import tempfile
import subprocess
import os
import re

__all__ = ['apply_patch_to_code']

def fix_patch_header(source_code: str, bad_patch: str) -> str:
    """
    自动修复只有 '@@' 而没有数字的 Patch。
    需要提供源代码来反向查找行号。
    """
    src_lines = source_code.splitlines()
    patch_lines = bad_patch.splitlines()
    
    # 结果容器
    fixed_patch_lines = []
    
    # 指针
    i = 0
    while i < len(patch_lines):
        line = patch_lines[i]
        
        # 找到一个 Hunk 的开始
        if line.strip() == '@@' or line.strip() == '@@@@':
            # --- 开始处理这个 Hunk ---
            hunk_content_lines = []
            
            # 收集 Hunk 的所有内容行（直到下一个 @@ 或文件结束）
            j = i + 1
            while j < len(patch_lines):
                if patch_lines[j].startswith('@@'):
                    break
                hunk_content_lines.append(patch_lines[j])
                j += 1
            
            # 提取用于在源码中搜索的“旧代码块” (Search Block)
            # 包含：上下文行(' ') 和 删除行('-')
            search_block = []
            
            # 统计长度
            old_len = 0
            new_len = 0
            
            for hl in hunk_content_lines:
                if hl.startswith('-'):
                    search_block.append(hl[1:]) # 去掉前导符号
                    old_len += 1
                elif hl.startswith('+'):
                    new_len += 1
                elif hl.startswith(' '):
                    search_block.append(hl[1:])
                    old_len += 1
                    new_len += 1
                else:
                    # 容错：有些空行 LLM 没加前导空格，或者其他奇怪情况
                    # 假设它是上下文
                    search_block.append(hl)
                    old_len += 1
                    new_len += 1

            # --- 关键步骤：在源码中定位 Search Block ---
            start_line = -1
            
            # 使用“指纹匹配”忽略缩进差异
            def get_fingerprint(s):
                return re.sub(r'\s+', '', s)
            
            if not search_block:
                # 这是一个纯新增的 Hunk (只有 +)，很难定位。
                # 这种情况下通常假设在文件末尾，或者无法修复。
                # 这里为了简单，假设它匹配失败，保留原样或设为 1
                start_line = 1 
            else:
                search_fp = [get_fingerprint(l) for l in search_block]
                n_search = len(search_fp)
                
                # 滑动窗口搜索
                for idx in range(len(src_lines) - n_search + 1):
                    match = True
                    for k in range(n_search):
                        if get_fingerprint(src_lines[idx+k]) != search_fp[k]:
                            match = False
                            break
                    if match:
                        start_line = idx + 1 # Patch 行号从 1 开始
                        break
            
            if start_line == -1:
                fixed_patch_lines.append(line) # 没救了，放回去
            else:
                # 生成标准的 Header
                # 格式: @@ -start,old_len +start,new_len @@
                new_header = f"@@ -{start_line},{old_len} +{start_line},{new_len} @@"
                fixed_patch_lines.append(new_header)
            
            # 把刚才收集的内容行放进去
            fixed_patch_lines.extend(hunk_content_lines)
            
            # 移动指针 j
            i = j
        else:
            # 文件头或其他信息 (--- / +++)
            fixed_patch_lines.append(line)
            i += 1
            
    return '\n'.join(fixed_patch_lines) + '\n'

def sanitize_patch_header(patch_text: str) -> str:
    """
    修正 Patch Header 中的行数统计错误。
    LLM 经常写错 @@ -old,len +new,len @@ 中的 len。
    我们将重新统计实际的行数，并覆盖 Header。
    """
    lines = patch_text.splitlines()
    if not lines:
        return patch_text

    # 1. 确保最后有空行（解决 unexpected end of file 的次要原因）
    if not patch_text.endswith('\n'):
        patch_text += '\n'
        lines = patch_text.splitlines()

    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 寻找 Header 行
        match = re.match(r'^@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', line)
        if match:
            # 找到 Header，开始统计下面这个 Hunk 的实际行数
            start_old = match.group(1)
            start_new = match.group(3)
            
            # 统计 Hunk 内容
            hunk_old_count = 0
            hunk_new_count = 0
            hunk_content = []
            
            i += 1
            while i < len(lines):
                next_line = lines[i]
                # 如果遇到下一个 Header，或者文件结束，停止统计
                if next_line.startswith('@@ '):
                    break
                
                hunk_content.append(next_line)
                
                if next_line.startswith('-'):
                    hunk_old_count += 1
                elif next_line.startswith('+'):
                    hunk_new_count += 1
                elif next_line.startswith(' ') or next_line == '':
                    # 空格行或空行通常算作上下文，既属于旧也属于新
                    hunk_old_count += 1
                    hunk_new_count += 1
                elif next_line.startswith('\\'): 
                    # \ No newline at end of file，不计数
                    pass
                else:
                    # 遇到无法识别的行，可能是 LLM 乱输出的注释，保守起见视作上下文
                    # 或者直接 break？通常视作上下文比较安全
                    hunk_old_count += 1
                    hunk_new_count += 1
                
                i += 1
            
            # 构造修正后的 Header
            # 格式：@@ -start,old_count +start,new_count @@
            # 注意：如果 count 是 1，通常标准 diff 会省略 ,1，但加上也没错
            fixed_header = f"@@ -{start_old},{hunk_old_count} +{start_new},{hunk_new_count} @@"
            
            new_lines.append(fixed_header)
            new_lines.extend(hunk_content)
            
            # 因为 while 内部已经 i++ 到了下一个块的开头，这里不需要再 i++
            continue
        else:
            # 不是 Header 也不是 Hunk 内容（可能是文件头 ---/+++），直接保留
            new_lines.append(line)
            i += 1
            
    return '\n'.join(new_lines) + '\n'

def apply_patch_to_code(code: str, patch_text: str) -> str:
    """
    使用系统 `patch` 命令将 patch_text 应用到 code。
    支持 fuzz=5 (忽略5行上下文差异) 和 batch 模式。
    """
    
    if not patch_text.endswith('\n'):
        patch_text += '\n'
    code = code.replace('\r\n', '\n')
    patch_text = patch_text.replace('\r\n', '\n')
    
    patch_text = fix_patch_header(code, patch_text)
    patch_text = sanitize_patch_header(patch_text)
    # 1. 创建临时文件存放源代码
    # delete=False 是必须的，因为我们要关闭文件后让 subprocess 去读写它
    with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False, encoding='utf-8') as src_f:
        src_f.write(code)
        src_path = src_f.name

    # 2. 创建临时文件存放 Patch 内容
    with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False, encoding='utf-8') as patch_f:
        patch_f.write(patch_text)
        patch_path = patch_f.name

    try:
        # 3. 构造 patch 命令
        # 语法: patch [options] [originalfile] -i [patchfile]
        cmd = [
            'patch',
            '--batch',       # 批处理模式，不询问用户
            '--fuzz=5',      # 允许最多 5 行上下文不匹配
            '-l',
            src_path,        # 指定要修改的目标文件 (忽略 patch 里的文件名)
            '-i', patch_path # 输入的 patch 文件
        ]

        # 4. 执行命令
        # capture_output=True 用于捕获报错信息
        result = subprocess.run(cmd, capture_output=True, text=True)

        # 5. 检查结果
        # 如果 returncode 不为 0，或者输出了 FAILED，通常表示失败
        if result.returncode != 0:
            raise ValueError(f"Failed to apply patch via command line.\n"
                             f"Return Code: {result.returncode}\n"
                             f"Stdout: {result.stdout}\n"
                             f"Stderr: {result.stderr}")

        # 6. 读取修改后的文件内容
        with open(src_path, 'r', encoding='utf-8') as f:
            new_code = f.read()
            
        return new_code

    finally:
        # 7. 清理所有临时文件
        if os.path.exists(src_path):
            os.remove(src_path)
        if os.path.exists(patch_path):
            os.remove(patch_path)
        
        # patch 命令失败时可能会生成垃圾文件，顺手清理
        if os.path.exists(src_path + ".rej"):
            os.remove(src_path + ".rej")
        if os.path.exists(src_path + ".orig"):
            os.remove(src_path + ".orig")
