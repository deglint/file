#!/usr/bin/env python3
"""
韩国电视频道同步脚本
自动从多个源同步频道信息到kr.m3u文件
"""

import json
import yaml
import xml.etree.ElementTree as ET
import requests
import re
import os
import sys
from urllib.parse import urlparse

class ChannelSync:
    def __init__(self):
        self.koreatv_json = None
        self.koreatv_epg = None
        self.backup_m3u = None
        self.channels_config = []
        
    def load_config(self):
        """加载频道配置"""
        try:
            # 尝试多个可能的配置文件路径
            config_paths = [
                'channels-config.yml',  # 根目录
                '.github/channels-config.yml'  # .github目录
            ]
            
            config_path = None
            for path in config_paths:
                if os.path.exists(path):
                    config_path = path
                    break
                    
            if not config_path:
                print("✗ 找不到配置文件，尝试路径:")
                for path in config_paths:
                    print(f"  - {path}")
                return False
                
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                self.channels_config = config.get('channels', [])
            print(f"✓ 从 {config_path} 加载了 {len(self.channels_config)} 个频道配置")
            return True
        except Exception as e:
            print(f"✗ 加载配置失败: {e}")
            return False
    
    def fetch_data(self):
        """获取所有数据源"""
        # 1. 获取koreatv.json
        try:
            response = requests.get(
                'https://raw.githubusercontent.com/kenpark76/kenpark76.github.io/main/koreatv.json',
                timeout=10
            )
            self.koreatv_json = response.json()
            print("✓ 获取koreatv.json成功")
        except Exception as e:
            print(f"✗ 获取koreatv.json失败: {e}")
            self.koreatv_json = []
        
        # 2. 获取koreatvEPG.xml
        try:
            response = requests.get(
                'https://raw.githubusercontent.com/kenpark76/kenpark76.github.io/main/koreatvEPG.xml',
                timeout=10
            )
            self.koreatv_epg = response.text
            print("✓ 获取koreatvEPG.xml成功")
        except Exception as e:
            print(f"✗ 获取koreatvEPG.xml失败: {e}")
            self.koreatv_epg = ""
        
        # 3. 获取备用源（如果需要）
        need_backup = any(channel.get('backup_source', False) for channel in self.channels_config)
        if need_backup:
            try:
                response = requests.get(
                    'https://raw.githubusercontent.com/iptv-org/iptv/master/streams/kr.m3u',
                    timeout=10
                )
                self.backup_m3u = response.text
                print("✓ 获取备用源kr.m3u成功")
            except Exception as e:
                print(f"✗ 获取备用源kr.m3u失败: {e}")
                self.backup_m3u = ""
        else:
            print("ℹ 没有频道需要备用源，跳过获取")
    
    def extract_channel_id_from_epg(self, epg_match):
        """从EPG XML中提取频道ID"""
        if not self.koreatv_epg:
            return None
        
        try:
            # 查找包含指定名称的channel元素
            pattern = f'<channel id="([^"]+)"[^>]*>\\s*<display-name>{re.escape(epg_match)}</display-name>'
            match = re.search(pattern, self.koreatv_epg)
            if match:
                return match.group(1)
            
            # 尝试第二种模式
            pattern = f'<channel id="([^"]+)">\\s*<display-name>{re.escape(epg_match)}</display-name>'
            match = re.search(pattern, self.koreatv_epg)
            return match.group(1) if match else None
        except Exception as e:
            print(f"✗ 解析EPG失败 {epg_match}: {e}")
            return None
    
    def extract_info_from_json(self, json_match):
        """从koreatv.json提取频道信息"""
        if not self.koreatv_json:
            return None, None
        
        try:
            for channel in self.koreatv_json:
                if channel.get('name') == json_match:
                    # 获取URL
                    uris = channel.get('uris', [])
                    url = uris[0] if uris else channel.get('url')
                    
                    # 获取logo
                    logo = channel.get('logo', '')
                    
                    return url, logo
            return None, None
        except Exception as e:
            print(f"✗ 从JSON提取信息失败 {json_match}: {e}")
            return None, None
    
    def extract_info_from_backup(self, backup_match):
        """从备用源提取频道信息"""
        if not self.backup_m3u:
            return None, None
        
        try:
            lines = self.backup_m3u.split('\n')
            for i, line in enumerate(lines):
                if line.startswith('#EXTINF:') and backup_match in line:
                    # 找到EXTINF行，下一行应该是URL
                    if i + 1 < len(lines):
                        url = lines[i + 1]
                        
                        # 尝试从EXTINF行提取logo
                        logo_match = re.search(r'tvg-logo="([^"]+)"', line)
                        logo = logo_match.group(1) if logo_match else ''
                        
                        return url, logo
            return None, None
        except Exception as e:
            print(f"✗ 从备用源提取信息失败 {backup_match}: {e}")
            return None, None
    
    def process_channels(self):
        """处理所有频道"""
        channel_results = []
        
        for channel in self.channels_config:
            name = channel['name']
            json_match = channel['json_match']
            epg_match = channel['epg_match']
            default_id = channel.get('default_id', '')
            backup_source = channel.get('backup_source', False)
            backup_match = channel.get('backup_match', json_match)
            
            print(f"\n处理频道: {name}")
            print(f"  JSON匹配: {json_match}")
            print(f"  EPG匹配: {epg_match}")
            
            # 1. 提取频道ID
            channel_id = self.extract_channel_id_from_epg(epg_match)
            if not channel_id:
                channel_id = default_id
                print(f"  使用默认频道ID: {channel_id}")
            else:
                print(f"  获取到频道ID: {channel_id}")
            
            # 2. 从主源提取URL和logo
            url, logo = self.extract_info_from_json(json_match)
            
            # 3. 如果主源失败且配置了备用源，尝试备用源
            if (not url or url == 'null') and backup_source:
                print(f"  主源未找到，尝试备用源...")
                backup_url, backup_logo = self.extract_info_from_backup(backup_match)
                
                if backup_url:
                    url = backup_url
                    if backup_logo and (not logo or logo == 'null'):
                        logo = backup_logo
                    print(f"  从备用源获取URL成功")
            
            # 4. 验证结果
            if not url or url == 'null':
                print(f"  ⚠ 警告: 未找到播放URL")
                url = None
            
            if not logo or logo == 'null':
                print(f"  ⚠ 警告: 未找到logo")
                logo = ''
            
            # 5. 保存结果
            if url:
                channel_results.append({
                    'name': name,
                    'channel_id': channel_id,
                    'url': url,
                    'logo': logo,
                    'success': True
                })
                print(f"  ✓ 成功提取频道信息")
            else:
                channel_results.append({
                    'name': name,
                    'success': False
                })
                print(f"  ✗ 频道信息提取失败")
        
        return channel_results
    
    def update_m3u_file(self, channel_results):
        """更新kr.m3u文件"""
        try:
            # 读取现有文件
            if not os.path.exists('kr.m3u'):
                print("ℹ kr.m3u文件不存在，创建新文件")
                content = "#EXTM3U\n"
            else:
                with open('kr.m3u', 'r', encoding='utf-8') as f:
                    content = f.read()
            
            # 去除重复频道
            lines = content.split('\n')
            cleaned_lines = []
            seen_channels = set()
            current_extinf = None
            
            for i, line in enumerate(lines):
                if line.startswith('#EXTINF:'):
                    # 提取频道名称
                    match = re.search(r',([^,]+)$', line)
                    if match:
                        channel_name = match.group(1).strip()
                        if channel_name in seen_channels:
                            # 跳过这个重复频道
                            current_extinf = 'skip'
                            continue
                        seen_channels.add(channel_name)
                        current_extinf = channel_name
                    cleaned_lines.append(line)
                elif line.startswith('http'):
                    if current_extinf == 'skip':
                        # 跳过重复频道的URL
                        current_extinf = None
                        continue
                    cleaned_lines.append(line)
                    current_extinf = None
                else:
                    cleaned_lines.append(line)
            
            # 构建新内容
            new_content = '\n'.join(cleaned_lines).strip()
            
            # 为每个成功获取的频道添加或更新
            for channel in channel_results:
                if not channel['success']:
                    continue
                
                name = channel['name']
                channel_id = channel['channel_id']
                url = channel['url']
                logo = channel['logo']
                
                # 构建EXTINF行
                if logo:
                    extinf_line = f'#EXTINF:-1 tvg-id="{channel_id}" tvg-logo="{logo}",{name}'
                else:
                    extinf_line = f'#EXTINF:-1 tvg-id="{channel_id}",{name}'
                
                # 检查是否已存在
                pattern = f'#EXTINF:[^\\n]*,{re.escape(name)}\\n'
                if re.search(pattern, new_content):
                    # 更新现有频道
                    new_content = re.sub(
                        pattern,
                        f'{extinf_line}\n',
                        new_content
                    )
                    
                    # 更新URL（下一行）
                    url_pattern = f'(#EXTINF:[^\\n]*,{re.escape(name)})\\n[^\\n]*\\n'
                    new_content = re.sub(
                        url_pattern,
                        f'{extinf_line}\n{url}\n',
                        new_content
                    )
                    print(f"✓ 更新频道: {name}")
                else:
                    # 添加新频道
                    new_content += f'\n\n{extinf_line}\n{url}'
                    print(f"✓ 添加频道: {name}")
            
            # 再次清理可能的重复
            final_lines = new_content.split('\n')
            final_cleaned = []
            seen_channels_final = set()
            current_extinf_final = None
            
            for line in final_lines:
                if line.startswith('#EXTINF:'):
                    match = re.search(r',([^,]+)$', line)
                    if match:
                        channel_name = match.group(1).strip()
                        if channel_name in seen_channels_final:
                            current_extinf_final = 'skip'
                            continue
                        seen_channels_final.add(channel_name)
                        current_extinf_final = channel_name
                    final_cleaned.append(line)
                elif line.startswith('http'):
                    if current_extinf_final == 'skip':
                        current_extinf_final = None
                        continue
                    final_cleaned.append(line)
                    current_extinf_final = None
                else:
                    final_cleaned.append(line)
            
            final_content = '\n'.join(final_cleaned).strip()
            
            # 确保以EXTM3U开头
            if not final_content.startswith('#EXTM3U'):
                final_content = '#EXTM3U\n' + final_content
            
            # 写入文件
            with open('kr.m3u', 'w', encoding='utf-8') as f:
                f.write(final_content)
            
            print(f"\n✓ 文件更新完成")
            return True
            
        except Exception as e:
            print(f"✗ 更新m3u文件失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run(self):
        """主运行函数"""
        print("=" * 60)
        print("韩国电视频道同步开始")
        print("=" * 60)
        
        # 1. 加载配置
        if not self.load_config():
            return False
        
        # 2. 获取数据
        self.fetch_data()
        
        # 3. 处理频道
        channel_results = self.process_channels()
        
        # 4. 统计
        success_count = sum(1 for c in channel_results if c['success'])
        print(f"\n" + "=" * 60)
        print(f"处理完成: {success_count}/{len(self.channels_config)} 个频道成功")
        
        # 5. 更新文件
        if success_count > 0:
            return self.update_m3u_file(channel_results)
        else:
            print("✗ 没有成功获取任何频道信息，跳过更新")
            return False

if __name__ == '__main__':
    sync = ChannelSync()
    success = sync.run()
    sys.exit(0 if success else 1)
