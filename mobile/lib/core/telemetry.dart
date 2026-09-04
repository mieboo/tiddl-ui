import 'dart:async';
import 'dart:math';
import 'package:shared_preferences/shared_preferences.dart';
import 'api_client.dart';

/// 移动端遥测:分账号、分设备、全操作事件上报。
///
/// - device_id: shared_preferences 持久化(跨会话稳定,标识"这台设备")
/// - session_id: 每次 App 启动生成(标识"这一次使用会话")
/// - 采集:播放/切音质/搜索/收藏/队列/登录登出等关键操作
/// - 上报:批量(10 条 或 8s 定时) -> POST /api/telemetry {device_id, session_id, events}
/// - 与网页端共用后端存储 telemetry/{account}/{date}.jsonl
class Telemetry {
  Telemetry._();
  static final Telemetry instance = Telemetry._();

  static const _kDeviceId = 'tiddl_device_id';
  final List<Map<String, dynamic>> _queue = [];
  Timer? _timer;
  String _deviceId = '';
  String _sessionId = '';
  bool _enabled = false;

  String get deviceId => _deviceId;
  String get sessionId => _sessionId;

  /// App 启动时调用:加载/生成设备 ID 与会话 ID。
  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _deviceId = prefs.getString(_kDeviceId) ?? '';
    if (_deviceId.isEmpty) {
      final rnd = Random();
      _deviceId = List.generate(32, (_) => rnd.nextInt(16).toRadixString(16)).join();
      await prefs.setString(_kDeviceId, _deviceId);
    }
    _sessionId =
        '${DateTime.now().millisecondsSinceEpoch.toRadixString(36)}${List.generate(6, (_) => Random().nextInt(16).toRadixString(16)).join()}';
  }

  /// 登录成功后启用(需要 token 才能上报)。
  void enable() {
    _enabled = true;
    trace('session.start', {'device_id': _deviceId, 'session_id': _sessionId});
  }

  /// 记录一条事件(fire-and-forget,不阻塞 UI)。
  void trace(String evt, [Map<String, dynamic>? data]) {
    if (!_enabled) return;
    _queue.add({
      't': DateTime.now().millisecondsSinceEpoch.toDouble(),
      'evt': evt,
      'data': data ?? {},
    });
    if (_queue.length >= 10) {
      _flush();
    } else {
      _timer ??= Timer(const Duration(seconds: 8), () {
        _timer = null;
        _flush();
      });
    }
  }

  void _flush() {
    if (_queue.isEmpty) return;
    final batch = List<Map<String, dynamic>>.from(_queue);
    _queue.clear();
    final api = ApiClient.instance;
    // fire-and-forget:失败静默,不重试
    api.postTelemetry({
      'device_id': _deviceId,
      'session_id': _sessionId,
      'events': batch,
    });
  }
}

/// 全局便捷入口:Telemetry.instance.trace(...) 太啰嗦,提供顶层函数。
Telemetry get telemetry => Telemetry.instance;
