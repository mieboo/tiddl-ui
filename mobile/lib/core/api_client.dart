import 'dart:convert';
import 'package:dio/dio.dart';
import '../core/config.dart';

/// 平台用户(后端 users.json)。
class AuthUser {
  final String username;
  final bool isAdmin;
  final bool enabled;
  final int plays;
  final int downloads;
  final bool totpEnabled;

  AuthUser({
    required this.username,
    required this.isAdmin,
    required this.enabled,
    required this.plays,
    required this.downloads,
    required this.totpEnabled,
  });

  factory AuthUser.fromJson(Map<String, dynamic> json) => AuthUser(
        username: json['username'] as String? ?? '',
        isAdmin: json['is_admin'] as bool? ?? false,
        enabled: json['enabled'] as bool? ?? true,
        plays: json['plays'] as int? ?? 0,
        downloads: json['downloads'] as int? ?? 0,
        totpEnabled: json['totp_enabled'] as bool? ?? false,
      );
}

/// Tidal 账号池信息(管理员可见)。
class TidalAccount {
  final String id;
  final String? username;
  final String? countryCode;
  final bool enabled;
  final String healthStatus;
  final String subscription;

  TidalAccount({
    required this.id,
    this.username,
    this.countryCode,
    required this.enabled,
    required this.healthStatus,
    required this.subscription,
  });

  factory TidalAccount.fromJson(Map<String, dynamic> json) => TidalAccount(
        id: json['id'] as String? ?? '',
        username: json['username'] as String?,
        countryCode: json['country_code'] as String?,
        enabled: json['enabled'] as bool? ?? true,
        healthStatus: json['health_status'] as String? ?? 'unknown',
        subscription: json['subscription'] as String? ?? 'unknown',
      );
}

/// 移动端解析结果(单曲/专辑的 v1 明文流)。
class MobileTrack {
  final String trackId;
  final String title;
  final String artist;
  final String album;
  final String albumId;
  final String? cover;
  final int? duration;
  final String codec;
  final String audioMode;
  final String mimeType;
  final String extension;
  final String quality;
  final String url;

  MobileTrack({
    required this.trackId,
    required this.title,
    required this.artist,
    required this.album,
    this.albumId = '',
    this.cover,
    this.duration,
    required this.codec,
    required this.audioMode,
    required this.mimeType,
    required this.extension,
    required this.quality,
    required this.url,
  });

  bool get isAtmos => audioMode == 'DOLBY_ATMOS';
  bool get isLossless => extension == '.flac' || codec == 'flac';

  factory MobileTrack.fromJson(Map<String, dynamic> json) => MobileTrack(
        trackId: json['track_id'] as String? ?? '',
        title: json['title'] as String? ?? '',
        artist: json['artist'] as String? ?? '',
        album: json['album'] as String? ?? '',
        albumId: (json['album_id'] ?? '').toString(),
        cover: json['cover'] as String?,
        duration: json['duration'] as int?,
        codec: json['codec'] as String? ?? 'aac',
        audioMode: json['audio_mode'] as String? ?? 'STEREO',
        mimeType: json['mime_type'] as String? ?? 'audio/mp4',
        extension: json['extension'] as String? ?? '.m4a',
        quality: json['quality'] as String? ?? 'HIGH',
        url: json['url'] as String? ?? '',
      );
}

/// 搜索结果条目。
class SearchResult {
  final String resource;
  final String type;
  final String title;
  final String subtitle;
  final String? cover;

  SearchResult({
    required this.resource,
    required this.type,
    required this.title,
    required this.subtitle,
    this.cover,
  });

  factory SearchResult.fromJson(Map<String, dynamic> json) => SearchResult(
        resource: json['resource'] as String? ?? '',
        type: json['type'] as String? ?? '',
        title: json['title'] as String? ?? '',
        subtitle: json['subtitle'] as String? ?? '',
        cover: json['cover'] as String?,
      );
}

/// 统一的 API 客户端:登录/登出/搜索/资源解析/移动端流解析。
class ApiClient {
  ApiClient._();
  static final ApiClient instance = ApiClient._();

  final Dio _dio = Dio(BaseOptions(
    connectTimeout: const Duration(seconds: 15),
    receiveTimeout: const Duration(seconds: 30),
  ));

  String? _token;
  AuthUser? _user;

  AuthUser? get user => _user;
  bool get isLoggedIn => _token != null;

  /// 登录;totp 可选(管理员启用双因素时传入)。
  Future<AuthUser> login(String username, String password, {String? totp}) async {
    final resp = await _dio.post(
      AppConfig.url('/api/user/login'),
      data: jsonEncode({'username': username, 'password': password, 'totp': totp}),
      options: Options(headers: {'Content-Type': 'application/json'}),
    );
    final body = resp.data as Map<String, dynamic>;
    _user = AuthUser.fromJson(body);
    _token = _cookieFrom(resp);
    // 后端用 HttpOnly cookie;dio 手动存 cookie 以便后续请求携带
    return _user!;
  }

  Future<void> logout() async {
    try { await _dio.post(AppConfig.url('/api/user/logout')); } catch (_) {}
    _token = null;
    _user = null;
  }

  /// 恢复会话(启动时探测)。
  Future<bool> restore() async {
    try {
      final resp = await _dio.get(
        AppConfig.url('/api/user/me'),
        options: Options(headers: _headers),
      );
      if (resp.statusCode == 200) {
        _user = AuthUser.fromJson(resp.data as Map<String, dynamic>);
        return true;
      }
    } catch (_) {}
    return false;
  }

  Map<String, String> get _headers {
    final h = <String, String>{'Content-Type': 'application/json'};
    if (_token != null) h['Cookie'] = _token!;
    return h;
  }

  String? _cookieFrom(Response resp) {
    final raw = resp.headers.value('set-cookie');
    if (raw == null) return null;
    // tiddl_session=<value>; Path=/; HttpOnly; ...
    final m = RegExp(r'(tiddl_session=[^;]+)').firstMatch(raw);
    return m?.group(1);
  }

  /// 遥测上报(fire-and-forget;未登录/失败静默,不阻塞 UI)。
  Future<void> postTelemetry(Map<String, dynamic> body) async {
    try {
      await _dio.post(
        AppConfig.url('/api/telemetry'),
        data: jsonEncode(body),
        options: Options(headers: _headers),
      );
    } catch (_) {/* 遥测失败不打扰用户 */}
  }

  /// 搜索(曲目/专辑/艺术家)。
  Future<List<SearchResult>> search(String query) async {
    final resp = await _dio.get(
      AppConfig.url('/api/search'),
      queryParameters: {'query': query},
      options: Options(headers: _headers),
    );
    final results = (resp.data as Map<String, dynamic>)['results'] as List;
    return results.map((e) => SearchResult.fromJson(e as Map<String, dynamic>)).toList();
  }

  /// 移动端流解析:资源 → v1 明文流清单(FLAC/AAC/eac3)。
  /// 用于小批量(单曲/专辑);大歌单请用 [stream] 逐首按需解析,避免一次大量请求触发限流。
  Future<List<MobileTrack>> resolve(List<String> urls, {String quality = 'high'}) async {
    final resp = await _dio.post(
      AppConfig.url('/api/mobile/resolve'),
      data: jsonEncode({'urls': urls, 'track_quality': quality}),
      options: Options(headers: _headers),
    );
    final tracks = (resp.data as Map<String, dynamic>)['tracks'] as List;
    return tracks.map((e) => MobileTrack.fromJson(e as Map<String, dynamic>)).toList();
  }

  /// 单曲按需解析(播放/下载某首时调用,一次 Tidal 请求,限流友好)。
  Future<MobileTrack> stream(String trackId, {String quality = 'high'}) async {
    final resp = await _dio.post(
      AppConfig.url('/api/mobile/stream'),
      data: jsonEncode({'track_id': trackId, 'track_quality': quality}),
      options: Options(headers: _headers),
    );
    return MobileTrack.fromJson(resp.data as Map<String, dynamic>);
  }

  /// 获取歌词(带时间轴字幕可选)。
  Future<LyricsData> lyrics(String trackId) async {
    final resp = await _dio.get(
      AppConfig.url('/api/mobile/lyrics/$trackId'),
      options: Options(headers: _headers),
    );
    final body = resp.data as Map<String, dynamic>;
    return LyricsData(
      lyrics: body['lyrics'] as String? ?? '',
      subtitles: body['subtitles'] as String? ?? '',
      rtl: body['rtl'] as bool? ?? false,
    );
  }

  /// 艺术家详情:专辑/单曲/参与曲目。
  Future<ArtistDetail> artist(String artistId) async {
    final resp = await _dio.get(
      AppConfig.url('/api/player/artist/$artistId'),
      options: Options(headers: _headers),
    );
    final b = resp.data as Map<String, dynamic>;
    return ArtistDetail(
      id: (b['id'] ?? '').toString(),
      name: b['name'] as String? ?? '',
      picture: b['picture'] as String?,
      albums: ((b['albums'] as List?) ?? []).map((e) => ArtistAlbum.fromJson(e as Map<String, dynamic>)).toList(),
      singles: ((b['singles'] as List?) ?? []).map((e) => ArtistAlbum.fromJson(e as Map<String, dynamic>)).toList(),
      tracks: ((b['tracks'] as List?) ?? []).map((e) => TrackEntry.fromJson(e as Map<String, dynamic>)).toList(),
    );
  }
}

class ArtistAlbum {
  final String id;
  final String title;
  final String artist;
  final String? cover;
  final int trackCount;
  final int? duration;
  final String? year;
  ArtistAlbum({required this.id, required this.title, required this.artist, this.cover, this.trackCount = 0, this.duration, this.year});

  factory ArtistAlbum.fromJson(Map<String, dynamic> j) => ArtistAlbum(
        id: (j['id'] ?? '').toString(),
        title: j['title'] as String? ?? '',
        artist: j['artist'] as String? ?? '',
        cover: j['cover'] as String?,
        trackCount: j['track_count'] as int? ?? 0,
        duration: j['duration'] as int?,
        year: j['year'] as String?,
      );
}

class TrackEntry {
  final String id;
  final String title;
  final String artist;
  final String album;
  final String? cover;
  final int? duration;
  TrackEntry({required this.id, required this.title, required this.artist, required this.album, this.cover, this.duration});

  factory TrackEntry.fromJson(Map<String, dynamic> j) => TrackEntry(
        id: (j['id'] ?? '').toString(),
        title: j['title'] as String? ?? '',
        artist: j['artist'] as String? ?? '',
        album: j['album'] as String? ?? '',
        cover: j['cover'] as String?,
        duration: j['duration'] as int?,
      );
}

class ArtistDetail {
  final String id;
  final String name;
  final String? picture;
  final List<ArtistAlbum> albums;
  final List<ArtistAlbum> singles;
  final List<TrackEntry> tracks;
  ArtistDetail({required this.id, required this.name, this.picture, required this.albums, required this.singles, required this.tracks});
}

class LyricsData {
  final String lyrics;
  final String subtitles;
  final bool rtl;
  const LyricsData({required this.lyrics, required this.subtitles, required this.rtl});

  bool get isEmpty => lyrics.trim().isEmpty;
}
