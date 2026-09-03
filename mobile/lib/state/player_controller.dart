import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:media_kit/media_kit.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../core/api_client.dart';
import '../models/library.dart';

/// 状态中枢:队列(单曲+专辑混排)、收藏(两级+排除)、关注、播放器实例、持久化。
/// 完整复刻网页版"收藏⇄队列"联动语义:
///  - 队列是扁平曲目列表,渲染时按 _sourceKey 分组(单曲独立/专辑折叠组)
///  - 收藏分"单曲"与"专辑"两级;收藏专辑自动合并其单曲收藏(favViaAlbum)
///  - 专辑内曲目可排除(_excluded);加入队列三态(full/partial/none)
///  - 取消收藏软删除(_pendingRemove),离开页才真正清理
class PlayerController extends ChangeNotifier {
  final ApiClient api;

  PlayerController(this.api) {
    _player.stream.playing.listen((_) => notifyListeners());
    _player.stream.position.listen((_) => notifyListeners());
    _player.stream.completed.listen((_) => next());
  }

  final Player _player = Player();
  Player get player => _player;

  Timer? _persistTimer;

  /// 任何队列/收藏/关注变更后延迟保存(防抖),避免频繁写盘。
  void _schedulePersist() {
    _persistTimer?.cancel();
    _persistTimer = Timer(const Duration(milliseconds: 800), () => persist());
  }

  // ---- 队列 ----
  List<QueueTrack> queue = [];
  int current = -1;
  bool shuffle = false;
  int repeat = 0; // 0=off 1=all 2=one
  final Set<String> openAlbums = {};

  // ---- 收藏/关注 ----
  List<FavoriteEntry> favorites = [];
  List<FollowArtist> follows = [];

  // ---- 队列成员判断 ----
  bool trackInQueue(String id) => queue.any((t) => t.id == id);

  /// 专辑入列三态:full=整张都在;partial=部分在;none=都不在。
  QueueState albumQueueState(FavoriteEntry entry) {
    final albumKey = 'album/${entry.id}';
    final cached = entry.tracks;
    if (cached != null && cached.isNotEmpty) {
      final total = cached.where((t) => !entry.excluded.contains(t.id)).toList();
      if (total.isEmpty) return QueueState.none;
      final ids = queue.map((t) => t.id).toSet();
      final hits = total.where((t) => ids.contains(t.id)).length;
      return hits == total.length ? QueueState.full : (hits > 0 ? QueueState.partial : QueueState.none);
    }
    return queue.any((t) => t.sourceType == 'album' && t.sourceKey == albumKey) ? QueueState.full : QueueState.none;
  }

  // ---- 播放 ----
  bool _resolving = false;

  /// 播放指定队列位:自动解析该曲的 v1 明文 URL 后播放。
  Future<void> playIndex(int index) async {
    if (_resolving) return;
    if (index < 0 || index >= queue.length) return;
    _resolving = true;
    current = index;
    notifyListeners();
    try {
      final t = queue[index];
      final mt = await api.stream(t.id);
      if (current != index) return; // 期间被用户切走,放弃
      await _player.open(Media(mt.url), play: true);
    } catch (e) {
      // 单曲解析失败:跳过
      if (current == index) {
        _player.stop();
        notifyListeners();
      }
    } finally {
      _resolving = false;
    }
  }

  /// 用已解析的明文 URL 播放指定队列位(供 UI 层已拿到 URL 的场景)。
  Future<void> playUrl(int index, String url) async {
    if (index < 0 || index >= queue.length) return;
    current = index;
    notifyListeners();
    await _player.open(Media(url), play: true);
  }

  Future<void> next() async {
    if (queue.isEmpty) return;
    if (repeat == 2) {
      await _player.seek(Duration.zero);
      await _player.play();
      return;
    }
    var i = current + 1;
    if (i >= queue.length) {
      if (repeat == 1) {
        i = 0;
      } else {
        return;
      }
    }
    if (i < queue.length) await playIndex(i);
  }

  Future<void> prev() async {
    if (queue.isEmpty) return;
    var i = current - 1;
    if (i < 0) i = queue.length - 1;
    if (i >= 0) await playIndex(i);
  }

  void toggleShuffle() {
    shuffle = !shuffle;
    notifyListeners();
    _schedulePersist();
  }

  void cycleRepeat() {
    repeat = (repeat + 1) % 3;
    notifyListeners();
    _schedulePersist();
  }

  // ---- 队列操作 ----
  void addTrack(MobileTrack t, {String sourceType = 'track', String? sourceKey}) {
    final item = QueueTrack.fromMobile(t, sourceType: sourceType, sourceKey: sourceKey);
    if (trackInQueue(t.trackId)) return;
    queue.add(item);
    notifyListeners();
    _schedulePersist();
  }

  /// 整张专辑加入队列(展开为其曲目,同 _sourceKey)。
  void addAlbumTracks(List<MobileTrack> tracks) {
    if (tracks.isEmpty) return;
    final first = tracks.first;
    final key = first.albumId.isNotEmpty ? 'album/${first.albumId}' : 'album/${first.album}';
    for (final t in tracks) {
      if (!trackInQueue(t.trackId)) queue.add(QueueTrack.fromMobile(t, sourceType: 'album', sourceKey: key));
    }
    notifyListeners();
    _schedulePersist();
  }

  /// 整张移除专辑(按 sourceKey 过滤)。
  void removeAlbumFromQueue(String key) {
    queue.removeWhere((t) => t.sourceKey == key);
    if (current >= queue.length) current = queue.length - 1;
    notifyListeners();
    _schedulePersist();
  }

  void removeFromQueue(int index) {
    if (index < 0 || index >= queue.length) return;
    queue.removeAt(index);
    if (index < current) {
      current--;
    }
    else if (index == current) {
      _player.pause();
      current = -1;
    }
    notifyListeners();
    _schedulePersist();
  }

  void clearQueue() {
    queue.clear();
    current = -1;
    openAlbums.clear();
    _player.pause();
    notifyListeners();
    _schedulePersist();
  }

  void toggleOpenAlbum(String key) {
    if (openAlbums.contains(key)) {
      openAlbums.remove(key);
    } else {
      openAlbums.add(key);
    }
    notifyListeners();
    _schedulePersist();
  }

  // ---- 收藏操作 ----
  bool isFavorite(String kind, String id) => favorites.any((e) => !e.pendingRemove && e.kind == kind && e.id == id);

  /// 单曲是否被某已收藏专辑覆盖(属专辑收藏的一部分)。
  bool isAlbumCovered(String albumId) =>
      albumId.isNotEmpty && favorites.any((e) => !e.pendingRemove && e.kind == 'album' && e.id == albumId);

  bool isTrackExcluded(String trackId, String albumId) {
    final album = favorites.firstWhere((e) => !e.pendingRemove && e.kind == 'album' && e.id == albumId, orElse: () => FavoriteEntry(kind: 'album', id: '', title: '', artist: ''));
    return album.excluded.contains(trackId);
  }

  bool isTrackFavorited(String trackId, String albumId) =>
      isFavorite('track', trackId) || (isAlbumCovered(albumId) && !isTrackExcluded(trackId, albumId));

  /// 收藏专辑:自动合并其单曲收藏(移除同专辑的单曲条目)。
  void addAlbumFavorite({required String id, required String title, required String artist, String? cover, int trackCount = 0}) {
    favorites.removeWhere((e) => e.kind == 'track' && e.albumId == id);
    favorites.removeWhere((e) => e.kind == 'album' && e.id == id);
    favorites.add(FavoriteEntry(kind: 'album', id: id, title: title, artist: artist, cover: cover, trackCount: trackCount));
    notifyListeners();
    _schedulePersist();
  }

  void toggleAlbumFavorite(FavoriteEntry entry) {
    final idx = favorites.indexWhere((e) => e.kind == 'album' && e.id == entry.id);
    if (idx >= 0) {
      if (favorites[idx].pendingRemove) {
        favorites[idx].pendingRemove = false;
      } else {
        favorites[idx].pendingRemove = true;
      }
      notifyListeners();
      _schedulePersist();
      return;
    }
    addAlbumFavorite(id: entry.id, title: entry.title, artist: entry.artist, cover: entry.cover, trackCount: entry.trackCount);
  }

  /// 收藏/取消收藏单曲。专辑已收藏时,点击心形 = 切换该曲的排除/恢复。
  bool toggleTrackFavorite(MobileTrack t) {
    final idx = favorites.indexWhere((e) => e.kind == 'track' && e.id == t.trackId);
    if (idx >= 0) {
      if (favorites[idx].pendingRemove) {
        favorites[idx].pendingRemove = false;
      } else {
        favorites[idx].pendingRemove = true;
      }
      notifyListeners();
      _schedulePersist();
      return true;
    }
    final album = favorites.firstWhere((e) => !e.pendingRemove && e.kind == 'album' && e.id == t.album, orElse: () => FavoriteEntry(kind: 'album', id: '', title: '', artist: ''));
    if (album.id.isNotEmpty) {
      // 专辑已收藏 → 切换排除/恢复
      final id = t.trackId;
      if (album.excluded.contains(id)) {
        album.excluded.remove(id);
      } else {
        album.excluded.add(id);
      }
      notifyListeners();
      _schedulePersist();
      return true;
    }
    favorites.add(FavoriteEntry(kind: 'track', id: t.trackId, title: t.title, artist: t.artist, album: t.album, albumId: t.album, cover: t.cover));
    notifyListeners();
    _schedulePersist();
    return true;
  }

  /// 软删除:取消收藏先打标记(条目仍在列表可撤销),离开页才真正清理。
  void setPendingRemove(FavoriteEntry entry, bool value) {
    entry.pendingRemove = value;
    notifyListeners();
    _schedulePersist();
  }

  /// 更新收藏专辑的缓存曲目(展开时懒加载)。
  void updateAlbumTracks(FavoriteEntry entry, List<QueueTrack> tracks) {
    entry.tracks = tracks;
    notifyListeners();
    _schedulePersist();
  }

  /// 软删除真正清理。
  void flushPendingRemoves() {
    favorites.removeWhere((e) => e.pendingRemove);
    notifyListeners();
    _schedulePersist();
  }

  // ---- 关注 ----
  bool isFollowing(String id) => follows.any((a) => a.id == id);

  void toggleFollowArtist(String id, String name, {String? picture}) {
    final idx = follows.indexWhere((a) => a.id == id);
    if (idx >= 0) {
      follows.removeAt(idx);
    } else {
      follows.add(FollowArtist(id: id, name: name, picture: picture));
    }
    notifyListeners();
    _schedulePersist();
  }

  // ---- 持久化 ----
  static const _kQueue = 'tiddl-player-queue';
  static const _kFavorites = 'tiddl-player-favorites';
  static const _kFollows = 'tiddl-player-follows';

  Future<void> persist() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kQueue, jsonEncode(queue.map((t) => t.toJson()).toList()));
    await prefs.setString(_kFavorites, jsonEncode(favorites.where((e) => !e.pendingRemove).map((e) => e.toJson()).toList()));
    await prefs.setString(_kFollows, jsonEncode(follows.map((a) => a.toJson()).toList()));
  }

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    try {
      final q = prefs.getString(_kQueue);
      if (q != null) queue = (jsonDecode(q) as List).map((e) => QueueTrack.fromJson(e as Map<String, dynamic>)).toList();
    } catch (_) {}
    try {
      final f = prefs.getString(_kFavorites);
      if (f != null) favorites = (jsonDecode(f) as List).map((e) => FavoriteEntry.fromJson(e as Map<String, dynamic>)).toList();
    } catch (_) {}
    try {
      final fo = prefs.getString(_kFollows);
      if (fo != null) follows = (jsonDecode(fo) as List).map((e) => FollowArtist.fromJson(e as Map<String, dynamic>)).toList();
    } catch (_) {}
    notifyListeners();
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }
}
