import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// 应用配置:后端地址(默认可在设置页修改)。
class AppConfig {
  AppConfig._();

  static const String _keyBase = 'tiddl_base_url';
  static const String defaultBaseUrl = 'http://10.0.2.2:8765'; // Android 模拟器访问宿主机

  static String _baseUrl = defaultBaseUrl;

  static String get baseUrl => _baseUrl;

  static Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    _baseUrl = prefs.getString(_keyBase) ?? defaultBaseUrl;
  }

  static Future<void> setBaseUrl(String url) async {
    final clean = url.trim().replaceAll(RegExp(r'/+$'), '');
    _baseUrl = clean.isEmpty ? defaultBaseUrl : clean;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyBase, _baseUrl);
  }

  /// 完整 URL 拼接:保证不含尾斜杠。
  static String url(String path) {
    final p = path.startsWith('/') ? path : '/$path';
    return '$_baseUrl$p';
  }

  /// 调试日志:仅 debug 构建输出。
  static void log(String message) {
    if (kDebugMode) debugPrint('[tiddl] $message');
  }
}
