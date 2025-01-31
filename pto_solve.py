import struct
import re

def _escape_message(s: bytes) -> str:
    """
    转义二进制消息中的特殊符号为人类可读标记
    """
    try:
        message = s.decode('shift-jis')
    except UnicodeDecodeError:
        return f"【无法解析：{s.hex()}】"

    # 替换复杂控制字符
    message = re.sub(r'\x07\x08([^\x07\x08]+?)\x00', r'{\1}', message)  # 转义 {标记}
    message = re.sub(r'\x07\x01([^\x07\x01]+?)\x0A([^\x0A]+?)\x00', r'[\1](\2)', message)  # 转义 [标记](附加内容)

    # 替换简单控制符
    return message.replace('\x07\x04', '[c]') \
                  .replace('\x07\x06', '[z]') \
                  .replace('\x07\x09', '[s]') \
                  .replace('\x0A', '[n]') \
                  .replace('\x0D', '[r]')


def _unescape_message(s: str) -> bytes:
    """
    将人类可读标记（[标记](附加内容)、[c]、[z] 等）还原为二进制消息。
    """
    # 初始化结果二进制
    result = b""

    # 正则处理复杂标记 [标记](附加内容)
    pattern = re.compile(r'\[([^[]+?)\]\(([^)]+?)\)')
    last_pos = 0
    for match in pattern.finditer(s):
        # 添加匹配前的普通字符串作为字节
        result += s[last_pos:match.start()].encode('shift-jis')
        # 添加复杂标记部分
        result += b'\x07\x01' + match.group(1).encode('shift-jis') + b'\x0A' + match.group(2).encode('shift-jis') + b'\x00'
        last_pos = match.end()

    # 添加未匹配的剩余部分
    result += s[last_pos:].encode('shift-jis')

    # 手动处理 {标记} -> \x07\x08<标记>\x00
    curly_pattern = re.compile(r'\{([^{}]+?)\}')
    last_pos = 0
    decoded_result = result.decode('shift-jis')  # 目前的结果解码为字符串
    binary_result = b""  # 最终的二进制结果
    for match in curly_pattern.finditer(decoded_result):
        # 添加 {标记} 之前的普通文本
        binary_result += decoded_result[last_pos:match.start()].encode('shift-jis')
        # 添加对应的 \x07\x08 标记
        binary_result += b'\x07\x08' + match.group(1).encode('shift-jis') + b'\x00'
        last_pos = match.end()

    # 添加剩余的内容
    binary_result += decoded_result[last_pos:].encode('shift-jis')

    # 替换简单标记为二进制
    binary_result = binary_result.replace(b'[c]', b'\x07\x04') \
                                 .replace(b'[z]', b'\x07\x06') \
                                 .replace(b'[s]', b'\x07\x09') \
                                 .replace(b'[n]', b'\x0A') \
                                 .replace(b'[r]', b'\x0D')

    return binary_result


def export_messages_dual_line(from_file, output_text_file, entries_start, entries_end, msg_start):
    """
    从指定的 exec.org.dat 文件中提取 msg_entries 和 msg 段，并以双行格式导出为 exec.msg.txt 文件。
    """
    with open(from_file, 'rb') as f:
        data = f.read()

    msg_entries = data[entries_start:entries_end]
    msg_data = data[msg_start:]

    # 每条记录 8 字节，解析 msg_entries
    entry_count = len(msg_entries) // 8
    entries = []
    for i in range(entry_count):
        offset, length = struct.unpack('<II', msg_entries[i * 8:(i + 1) * 8])
        entries.append((offset, length))

    # 提取所有消息
    messages = []
    for offset, length in entries:
        message_bytes = msg_data[offset:offset + length]
        escaped_message = _escape_message(message_bytes)
        messages.append(escaped_message)

    # 写入双行格式的文本文件
    with open(output_text_file, 'w', encoding='utf-8') as f:
        for i, message in enumerate(messages):
            f.write(f'◇{i:08X}◇{message}\n')
            f.write(f'◆{i:08X}◆{message}\n\n')

    print(f"Export successfully： {output_text_file}")


def import_messages_dual_line(input_text_file, original_file, output_file, entries_start, entries_end, msg_start):
    """
    从 exec.msg.txt 导入修改后的文本，生成新的 exec.org.dat 文件。
    """
    # 读取编辑后的文本文件
    messages = []
    with open(input_text_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('◆'):  # 只处理 ◆ 开头的行
                message = line.split('◆', 2)[2].strip()
                messages.append(message)

    # 开始重新计算偏移和长度
    new_msg = bytearray()
    new_entries = []
    current_offset = 0

    for message in messages:
        encoded_message = _unescape_message(message)  # 反转义 -> shift-jis 字节
        length = len(encoded_message)
        new_entries.append((current_offset, length))
        current_offset += length
        new_msg.extend(encoded_message)

    # 读取原始数据
    with open(original_file, 'rb') as f:
        original_data = bytearray(f.read())

    # 替换 msg_entries 段
    new_entries_data = b""
    for offset, length in new_entries:
        new_entries_data += struct.pack('<II', offset, length)

    # 覆盖原始文件的 `msg_entries` 和 `msg` 区段
    original_data[entries_start:entries_end] = new_entries_data
    original_data[msg_start:] = new_msg

    # 保存到新文件
    with open(output_file, 'wb') as f:
        f.write(original_data)

    print(f"Import successfully：{output_file}")


if __name__ == '__main__':
    original_file = 'exec.org.dat'
    output_text_file = 'exec.msg.txt'
    new_file = 'new_exec.dat'

    # 手动提供的段信息
    entries_start = 0x33_8CED
    entries_end = 0x38_924D
    msg_start = 0x38_9251

    # 主菜单
    print("Choic:")
    print("1: Export message from exec.org.dat")
    print("2: Import exec.msg.txt to export new_exec.dat")
    choice = input(" 1 or 2：").strip()

    if choice == '1':
        export_messages_dual_line(original_file, output_text_file, entries_start, entries_end, msg_start)
    elif choice == '2':
        import_messages_dual_line(output_text_file, original_file, new_file, entries_start, entries_end, msg_start)
    else:
        print("Invalid input!")
