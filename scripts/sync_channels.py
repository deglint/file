#!/usr/bin/env python3
"""
韩国电视频道同步脚本 - 重建版本
根据配置文件完全重建kr.m3u文件，确保频道顺序和内容与配置完全一致
"""

import json
import yaml
import requests
import re
import os
import sys
from urllib.parse import urlparse
import difflib

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
            
            # 预解析EPG中的所有频道，用于模糊匹配
            self.parse_epg_channels()
            
        except Exception as e:
            print(f"✗ 获取koreatvEPG.xml失败: {e}")
            self.koreatv_epg = ""
            self.epg_channels = {}
        
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
    
    def parse_epg_channels(self):
        """解析EPG中的所有频道，用于快速查找"""
        self.epg_channels = {}
        
        if not self.koreatv_epg:
            return
        
        # 查找所有channel元素
        pattern = r'<channel id="([^"]+)"[^>]*>\s*<display-name>([^<]+)</display-name>'
        matches = re.findall(pattern, self.koreatv_epg)
        
        for channel_id, display_name in matches:
            self.epg_channels[display_name.strip()] = channel_id
        
        print(f"✓ 从EPG中解析了 {len(self.epg_channels)} 个频道")
    
    def find_channel_id(self, epg_match):
        """智能查找频道ID"""
        if not self.epg_channels:
            return None
        
        # 1. 精确匹配
        if epg_match in self.epg_channels:
            return self.epg_channels[epg_match]
        
        # 2. 尝试去除空格匹配（如"KBS1"匹配"KBS 1TV"）
        simplified_epg_match = epg_match.replace(' ', '')
        for epg_name, channel_id in self.epg_channels.items():
            if epg_name.replace(' ', '') == simplified_epg_match:
                print(f"  注意: 通过去除空格匹配: '{epg_match}' -> '{epg_name}'")
                return channel_id
        
        # 3. 模糊匹配（使用difflib）
        epg_names = list(self.epg_channels.keys())
        matches = difflib.get_close_matches(epg_match, epg_names, n=1, cutoff=0.6)
        
        if matches:
            matched_name = matches[0]
            similarity = difflib.SequenceMatcher(None, epg_match, matched_name).ratio()
            print(f"  注意: 使用模糊匹配: '{epg_match}' -> '{matched_name}' (相似度: {similarity:.2f})")
            return self.epg_channels[matched_name]
        
        # 4. 尝试部分匹配
        for epg_name, channel_id in self.epg_channels.items():
            if epg_match in epg_name or epg_name in epg_match:
                print(f"  注意: 通过部分匹配: '{epg_match}' -> '{epg_name}'")
                return channel_id
        
        return None
    
    def extract_channel_id_from_epg(self, epg_match):
        """从EPG XML中提取频道ID（增强版）"""
        if not self.koreatv_epg:
            return None
        
        # 首先尝试精确查找
        channel_id = self.find_channel_id(epg_match)
        
        if channel_id:
            return channel_id
        
        # 如果没找到，尝试正则表达式搜索
        try:
            # 尝试多种可能的格式
            patterns = [
                f'<channel id="([^"]+)"[^>]*>\\s*<display-name>{re.escape(epg_match)}</display-name>',
                f'<channel id="([^"]+)">\\s*<display-name>{re.escape(epg_match)}</display-name>',
                f'<channel id="([^"]+)".*?<display-name>{re.escape(epg_match)}</display-name>',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, self.koreatv_epg)
                if match:
                    return match.group(1)
            
            # 如果还没找到，尝试不区分大小写
            pattern = f'<channel id="([^"]+)".*?<display-name>{re.escape(epg_match)}</display-name>'
            match = re.search(pattern, self.koreatv_epg, re.IGNORECASE)
            if match:
                return match.group(1)
                
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
                if channel_id:
                    print(f"  使用默认频道ID: {channel_id}")
                else:
                    print(f"  ⚠ 警告: 未找到频道ID，将使用空值")
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
    
    def rebuild_m3u_file(self, channel_results):
        """完全重建kr.m3u文件，确保顺序与配置一致"""
        try:
            print(f"\n开始重建kr.m3u文件...")
            print(f"将包含 {len([c for c in channel_results if c['success']])} 个频道")
            
            # 构建新内容
            lines = []
            
            # 添加文件头
            lines.append("#EXTM3U")
            lines.append("")
            
            # 按照配置文件顺序添加频道
            added_count = 0
            for channel in channel_results:
                if not channel['success']:
                    continue
                
                name = channel['name']
                channel_id = channel['channel_id']
                url = channel['url']
                logo = channel['logo']
                
                # 构建EXTINF行
                if logo and logo != 'null':
                    extinf_line = f'#EXTINF:-1 tvg-id="{channel_id}" tvg-logo="{logo}",{name}'
                else:
                    extinf_line = f'#EXTINF:-1 tvg-id="{channel_id}",{name}'
                
                # 添加到文件
                lines.append(extinf_line)
                lines.append(url)
                lines.append("")  # 添加空行分隔
                
                added_count += 1
                print(f"✓ 添加频道到新文件: {name}")
            
            # 移除最后一个空行
            if lines and lines[-1] == "":
                lines.pop()
            
            # 写入文件
            new_content = "\n".join(lines)
            
            with open('kr.m3u', 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"\n✓ 文件重建完成")
            print(f"  成功添加了 {added_count} 个频道")
            print(f"  频道顺序与配置文件完全一致")
            return True
            
        except Exception as e:
            print(f"✗ 重建m3u文件失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run(self):
        """主运行函数"""
        print("=" * 60)
        print("韩国电视频道同步 - 完全重建版")
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
        
        # 5. 重建文件
        if success_count > 0:
            return self.rebuild_m3u_file(channel_results)
        else:
            print("✗ 没有成功获取任何频道信息，跳过更新")
            return False

if __name__ == '__main__':
    sync = ChannelSync()
    success = sync.run()
    sys.exit(0 if success else 1)
