import '../core/api_client.dart';

/// 队列/收藏三态(网页版: full/partial/none)。
enum QueueState { full, partial, none }

/// 队列成员:单曲或"专辑组内的一首"。
/// 与网页版一致:队列是扁平的曲目列表,每首带 _sourceType/_sourceKey,
/// 渲染时按 _sourceKey 分组(单曲各自成组,专辑成折叠组)。
class QueueTrack {
  final String id;
  final String title;
  final String artist;
  final String album;
  final String albumId;
  final String? cover;
  final int? duration;
  final int trackNumber;
  final String sourceType; // "track" | "album"
  final String sourceKey; // track/<id> 或 album/<id>

  QueueTrack({
    required this.id,
    required this.title,
    required this.artist,
    required this.album,
    required this.albumId,
    this.cover,
    this.duration,
    this.trackNumber = 0,
    this.sourceType = 'track',
    required this.sourceKey,
  });

  factory QueueTrack.fromMobile(MobileTrack t, {String sourceType = 'track', String? sourceKey}) => QueueTrack(
        id: t.trackId,
        title: t.title,
        artist: t.artist,
        album: t.album,
        albumId: t.albumId,
        cover: t.cover,
        duration: t.duration,
        sourceType: sourceType,
        sourceKey: sourceKey ?? (sourceType == 'album' ? 'album/${t.albumId.isNotEmpty ? t.albumId : t.album}' : 'track/${t.trackId}'),
      );

  Map<String, dynamic> toJson() => {
        'id': id,
        'title': title,
        'artist': artist,
        'album': album,
        'album_id': albumId,
        'cover': cover,
        'duration': duration,
        'track_number': trackNumber,
        'source_type': sourceType,
        'source_key': sourceKey,
      };

  factory QueueTrack.fromJson(Map<String, dynamic> j) => QueueTrack(
        id: (j['id'] ?? '').toString(),
        title: j['title'] as String? ?? '',
        artist: j['artist'] as String? ?? '',
        album: j['album'] as String? ?? '',
        albumId: (j['album_id'] ?? '').toString(),
        cover: j['cover'] as String?,
        duration: j['duration'] as int?,
        trackNumber: j['track_number'] as int? ?? 0,
        sourceType: j['source_type'] as String? ?? 'track',
        sourceKey: j['source_key'] as String? ?? 'track/${j['id']}',
      );
}

/// 收藏条目:单曲或专辑(两级结构)。
/// - kind=="album":持有 excluded(排除的曲目 id 集合)与 _tracks(缓存曲目)。
/// - pendingRemove:软删除标记(取消收藏后条目仍在列表,离开页面才真正清理)。
class FavoriteEntry {
  final String kind; // "track" | "album"
  final String id;
  final String title;
  final String artist;
  final String album;
  final String albumId;
  final String? cover;
  final int trackCount;
  final Set<String> excluded; // 专辑内被排除的曲目
  List<QueueTrack>? tracks; // 专辑展开时缓存的曲目
  bool pendingRemove;

  FavoriteEntry({
    required this.kind,
    required this.id,
    required this.title,
    required this.artist,
    this.album = '',
    this.albumId = '',
    this.cover,
    this.trackCount = 0,
    Set<String>? excluded,
    this.tracks,
    this.pendingRemove = false,
  }) : excluded = excluded ?? <String>{};

  /// 排除后实际有效曲目数。
  int get effectiveCount => trackCount > 0 ? trackCount - excluded.length : (tracks?.length ?? 0) - excluded.length;

  Map<String, dynamic> toJson() => {
        'kind': kind,
        'id': id,
        'title': title,
        'artist': artist,
        'album': album,
        'album_id': albumId,
        'cover': cover,
        'track_count': trackCount,
        'excluded': excluded.toList(),
      };

  factory FavoriteEntry.fromJson(Map<String, dynamic> j) => FavoriteEntry(
        kind: j['kind'] as String? ?? 'track',
        id: (j['id'] ?? '').toString(),
        title: j['title'] as String? ?? '',
        artist: j['artist'] as String? ?? '',
        album: j['album'] as String? ?? '',
        albumId: (j['album_id'] ?? '').toString(),
        cover: j['cover'] as String?,
        trackCount: j['track_count'] as int? ?? 0,
        excluded: ((j['excluded'] as List?) ?? []).map((e) => e.toString()).toSet(),
      );
}

/// 关注的艺术家。
class FollowArtist {
  final String id;
  final String name;
  final String? picture;

  FollowArtist({required this.id, required this.name, this.picture});

  Map<String, dynamic> toJson() => {'id': id, 'name': name, 'picture': picture};

  factory FollowArtist.fromJson(Map<String, dynamic> j) => FollowArtist(
        id: (j['id'] ?? '').toString(),
        name: j['name'] as String? ?? '',
        picture: j['picture'] as String?,
      );
}
