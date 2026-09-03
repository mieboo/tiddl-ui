import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/api_client.dart';
import '../downloads/downloads_screen.dart';
import '../models/library.dart';
import '../settings/settings_sheet.dart';
import '../state/player_controller.dart';
import 'artist_detail_screen.dart';

/// 左栏(网页版 library-panel):队列 / 收藏 / 关注 三内 Tab + 搜索。
/// 队列:单曲与专辑混排(专辑折叠组);收藏:两级(单曲/专辑)+排除;关注:艺术家。
class LeftPanel extends StatefulWidget {
  const LeftPanel({super.key});
  @override
  State<LeftPanel> createState() => _LeftPanelState();
}

class _LeftPanelState extends State<LeftPanel> {
  String _tab = 'playlist'; // playlist | favorites | following
  final TextEditingController _search = TextEditingController();
  List<SearchResult> _results = [];
  bool _searching = false;
  bool _searchMode = false;

  @override
  void initState() {
    super.initState();
    _search.addListener(_onSearchChanged);
  }

  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    _search.dispose();
    super.dispose();
  }

  void _onSearchChanged() {
    final q = _search.text.trim();
    // 收藏 Tab:本地过滤收藏(不走 API);其他 Tab:防抖后全局搜索
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), () {
      if (!mounted) return;
      setState(() {
        _searchMode = q.isNotEmpty;
        if (_tab != 'favorites' && q.length >= 2) {
          _doSearch(q);
        } else if (_tab != 'favorites') {
          _results = [];
        }
      });
    });
  }

  Future<void> _doSearch(String q) async {
    setState(() => _searching = true);
    try {
      final r = await ApiClient.instance.search(q);
      if (mounted) setState(() => _results = r);
    } catch (_) {
      // 搜索失败静默:显示空结果
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.watch<PlayerController>();
    return SafeArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _header(c),
          _tabs(c),
          _searchBar(),
          Expanded(child: _body(c)),
        ],
      ),
    );
  }

  Widget _header(PlayerController c) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 8, 0),
      child: Row(
        children: [
          const Expanded(
            child: Text('ATP', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined, size: 22),
            tooltip: 'Settings',
            onPressed: () => _showSettings(context, c),
          ),
        ],
      ),
    );
  }

  void _showSettings(BuildContext context, PlayerController c) {
    showModalBottomSheet(
      context: context,
      showDragHandle: true,
      builder: (_) => const SettingsSheet(),
    );
  }

  Widget _tabs(PlayerController c) {
    Widget tab(String key, String label, String count) {
      final active = _tab == key;
      return Expanded(
        child: InkWell(
          onTap: () => setState(() => _tab = key),
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 12),
            decoration: BoxDecoration(
              border: Border(bottom: BorderSide(color: active ? Theme.of(context).colorScheme.primary : Colors.transparent, width: 2)),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(label, style: TextStyle(fontWeight: active ? FontWeight.w600 : FontWeight.w400, color: active ? Theme.of(context).colorScheme.primary : Theme.of(context).colorScheme.onSurfaceVariant)),
                if (count.isNotEmpty) ...[
                  const SizedBox(width: 4),
                  Text(count, style: TextStyle(fontSize: 11, color: Theme.of(context).colorScheme.onSurfaceVariant)),
                ],
              ],
            ),
          ),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
      child: Row(
        children: [
          tab('playlist', 'Playlist', c.queue.length.toString()),
          tab('favorites', 'Favorites', c.favorites.where((e) => !e.pendingRemove).length.toString()),
          tab('artist', 'Artist', c.follows.length.toString()),
        ],
      ),
    );
  }

  Widget _searchBar() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
      child: TextField(
        controller: _search,
        textInputAction: TextInputAction.search,
        decoration: InputDecoration(
          hintText: _tab == 'favorites' ? 'Search your favorites' : 'Search tracks and albums, or paste a Tidal link',
          prefixIcon: const Icon(Icons.search, size: 20),
          isDense: true,
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
          suffixIcon: _searching ? const Padding(padding: EdgeInsets.all(12), child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))) : null,
        ),
      ),
    );
  }

  Widget _body(PlayerController c) {
    if (_searchMode && _tab != 'favorites') return _searchResults(c);
    switch (_tab) {
      case 'favorites':
        return _favoritesTab(c);
      case 'artist':
        return _artistTab(c);
      default:
        return _queueTab(c);
    }
  }

  // ---- 搜索 ----
  Widget _searchResults(PlayerController c) {
    if (_results.isEmpty) {
      return Center(child: Text('No results', style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)));
    }
    return ListView.separated(
      itemCount: _results.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (_, i) {
        final r = _results[i];
        final isFav = c.isFavorite(r.type, r.resource.split('/').last);
        return ListTile(
          dense: true,
          leading: r.cover != null ? ClipRRect(borderRadius: BorderRadius.circular(6), child: Image.network(r.cover!, width: 36, height: 36, fit: BoxFit.cover)) : const Icon(Icons.music_note),
          title: Text(r.title, maxLines: 1, overflow: TextOverflow.ellipsis),
          subtitle: Text(r.subtitle, maxLines: 1, overflow: TextOverflow.ellipsis),
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              IconButton(icon: Icon(isFav ? Icons.favorite : Icons.favorite_border, size: 18, color: isFav ? Colors.redAccent : null), onPressed: () => _toggleResultFav(c, r)),
              if (r.type == 'track' || r.type == 'album')
                IconButton(icon: const Icon(Icons.add_circle_outline, size: 18), onPressed: () => _addResult(c, r)),
            ],
          ),
          onTap: () {
            if (r.type == 'artist') {
              Navigator.of(context).push(MaterialPageRoute(builder: (_) => ArtistDetailScreen(artistId: r.resource.split('/').last, initialName: r.title)));
            } else if (r.type == 'track' || r.type == 'album') {
              _addResult(c, r);
            }
          },
        );
      },
    );
  }

  Future<void> _toggleResultFav(PlayerController c, SearchResult r) async {
    final [kind, id] = r.resource.split('/');
    if (c.isFavorite(kind, id)) {
      final entry = c.favorites.firstWhere((e) => e.kind == kind && e.id == id, orElse: () => FavoriteEntry(kind: kind, id: id, title: r.title, artist: r.subtitle));
      c.setPendingRemove(entry, true);
      return;
    }
    if (kind == 'album') {
      c.addAlbumFavorite(id: id, title: r.title, artist: r.subtitle, cover: r.cover);
    } else {
      try {
        final t = await ApiClient.instance.stream(id);
        if (!mounted) return;
        c.toggleTrackFavorite(t);
      } catch (_) {
        // 收藏失败静默:忽略该次操作
      }
    }
  }

  Future<void> _addResult(PlayerController c, SearchResult r) async {
    try {
      if (r.type == 'album') {
        final tracks = await ApiClient.instance.resolve([r.resource]);
        if (mounted) c.addAlbumTracks(tracks);
      } else {
        final t = await ApiClient.instance.stream(r.resource.split('/').last);
        if (mounted) c.addTrack(t);
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  // ---- 队列 Tab ----
  Widget _queueTab(PlayerController c) {
    if (c.queue.isEmpty) {
      return const _EmptyState(icon: Icons.queue_music, text: 'Search or paste a track or album link');
    }
    // 分组:单曲各自成组,专辑按 sourceKey 成折叠组
    final groups = <_QueueGroup>[];
    for (var i = 0; i < c.queue.length; i++) {
      final t = c.queue[i];
      final key = t.sourceType == 'album' ? t.sourceKey : 'track:${t.id}';
      _QueueGroup? g;
      for (final x in groups) {
        if (x.key == key) {
          g = x;
          break;
        }
      }
      if (g == null) {
        g = _QueueGroup(key: key, type: t.sourceType, items: []);
        groups.add(g);
      }
      g.items.add((t, i));
    }
    return ListView.builder(
      padding: const EdgeInsets.only(bottom: 60),
      itemCount: groups.length,
      itemBuilder: (_, gi) {
        final g = groups[gi];
        if (g.type != 'album') return _queueTrackRow(c, g.items.first.$1, g.items.first.$2);
        return _queueAlbumGroup(c, g);
      },
    );
  }

  Widget _queueAlbumGroup(PlayerController c, _QueueGroup g) {
    final first = g.items.first.$1;
    final key = g.key;
    final open = c.openAlbums.contains(key);
    final isFav = c.isFavorite('album', first.albumId);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        InkWell(
          onTap: () => c.toggleOpenAlbum(key),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(
              children: [
                if (first.cover != null) ClipRRect(borderRadius: BorderRadius.circular(6), child: Image.network(first.cover!, width: 40, height: 40, fit: BoxFit.cover)),
                const SizedBox(width: 10),
                Expanded(child: Text(first.album, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600))),
                Text('${g.items.length}', style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
                IconButton(iconSize: 18, icon: const Icon(Icons.download_outlined), onPressed: () => _downloadAlbum(c, first.albumId, first.album)),
                IconButton(iconSize: 18, icon: Icon(isFav ? Icons.favorite : Icons.favorite_border, color: isFav ? Colors.redAccent : null), onPressed: () => c.toggleAlbumFavorite(FavoriteEntry(kind: 'album', id: first.albumId, title: first.album, artist: first.artist, albumId: first.albumId, cover: first.cover))),
                IconButton(iconSize: 18, icon: const Icon(Icons.close), onPressed: () => c.removeAlbumFromQueue(key)),
                Icon(open ? Icons.expand_less : Icons.expand_more, size: 18),
              ],
            ),
          ),
        ),
        if (open)
          ...g.items.map((e) => _queueTrackRow(c, e.$1, e.$2, inner: true)),
      ],
    );
  }

  Widget _queueTrackRow(PlayerController c, QueueTrack t, int index, {bool inner = false}) {
    final fav = c.isTrackFavorited(t.id, t.albumId);
    return InkWell(
      onTap: () => c.playIndex(index),
      child: Container(
        padding: EdgeInsets.only(left: inner ? 30 : 12, right: 4, top: 6, bottom: 6),
        color: index == c.current ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.12) : null,
        child: Row(
          children: [
            SizedBox(width: 22, child: Text('${t.trackNumber != 0 ? t.trackNumber : index + 1}', style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant))),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(t.title, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 14)),
                  Text(t.artist, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 11, color: Theme.of(context).colorScheme.onSurfaceVariant)),
                ],
              ),
            ),
            IconButton(iconSize: 17, icon: Icon(fav ? Icons.favorite : Icons.favorite_border, color: fav ? Colors.redAccent : null), onPressed: () => c.toggleTrackFavorite(_mobileOf(t))),
            IconButton(
              iconSize: 17,
              icon: const Icon(Icons.download_outlined),
              onPressed: () async {
                final messenger = ScaffoldMessenger.maybeOf(context);
                try {
                  final mt = await ApiClient.instance.stream(t.id);
                  if (mounted) await DownloadsScreen.startDownload(messenger, mt);
                } catch (e) {
                  messenger?.showSnackBar(SnackBar(content: Text('Download failed: $e')));
                }
              },
            ),
            IconButton(iconSize: 17, icon: const Icon(Icons.close), onPressed: () => c.removeFromQueue(index)),
          ],
        ),
      ),
    );
  }

  MobileTrack _mobileOf(QueueTrack t) => MobileTrack(
        trackId: t.id,
        title: t.title,
        artist: t.artist,
        album: t.album,
        cover: t.cover,
        duration: t.duration,
        codec: '',
        audioMode: 'STEREO',
        mimeType: '',
        extension: '',
        quality: '',
        url: '',
      );

  // ---- 收藏 Tab ----
  Widget _favoritesTab(PlayerController c) {
    if (c.favorites.where((e) => !e.pendingRemove).isEmpty) {
      return const _EmptyState(icon: Icons.favorite, text: 'Tracks you favorite will appear here');
    }
    final entries = c.favorites.where((e) => !e.pendingRemove).toList();
    final terms = _search.text.trim().toLowerCase().split(RegExp(r'\s+')).where((e) => e.isNotEmpty).toList();
    final filtered = terms.isEmpty
        ? entries
        : entries.where((e) => terms.every((term) => '${e.title} ${e.artist} ${e.album}'.toLowerCase().contains(term))).toList();
    return ListView.builder(
      padding: const EdgeInsets.only(bottom: 60),
      itemCount: filtered.length,
      itemBuilder: (_, i) => _favoriteRow(c, filtered[i]),
    );
  }

  Widget _favoriteRow(PlayerController c, FavoriteEntry e) {
    if (e.kind == 'album') return _favoriteAlbumRow(c, e);
    return _favoriteTrackRow(c, e);
  }

  Widget _favoriteAlbumRow(PlayerController c, FavoriteEntry e) {
    final state = c.albumQueueState(e);
    final count = e.effectiveCount;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Row(
            children: [
              if (e.cover != null) ClipRRect(borderRadius: BorderRadius.circular(6), child: Image.network(e.cover!, width: 40, height: 40, fit: BoxFit.cover)),
              const SizedBox(width: 10),
              Expanded(child: Text(e.title, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w600))),
              if (count > 0) Text('$count', style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
              IconButton(iconSize: 18, icon: const Icon(Icons.download_outlined), onPressed: () => _downloadAlbum(c, e.id, e.title)),
              _queueToggle(c, state, onTap: () => _toggleAlbumInQueue(c, e)),
              IconButton(iconSize: 18, icon: const Icon(Icons.favorite, color: Colors.redAccent), onPressed: () => _softRemove(c, e)),
            ],
          ),
        ),
        if (e.tracks != null)
          ...e.tracks!.map((t) => _favInnerTrack(c, e, t)),
      ],
    );
  }

  Widget _favInnerTrack(PlayerController c, FavoriteEntry album, QueueTrack t) {
    final excluded = album.excluded.contains(t.id);
    final inQueue = c.trackInQueue(t.id);
    return Container(
      padding: const EdgeInsets.only(left: 30, right: 4),
      child: Row(
        children: [
          Expanded(child: Text(t.title, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 13, color: excluded ? Theme.of(context).colorScheme.onSurfaceVariant : null, decoration: excluded ? TextDecoration.lineThrough : null))),
          if (inQueue) Icon(Icons.check, size: 16, color: Theme.of(context).colorScheme.primary),
          IconButton(iconSize: 17, icon: Icon(excluded ? Icons.favorite_border : Icons.favorite, color: excluded ? null : Colors.redAccent), onPressed: () => c.toggleTrackFavorite(_mobileOf(t))),
        ],
      ),
    );
  }

  Widget _favoriteTrackRow(PlayerController c, FavoriteEntry e) {
    final inQueue = c.trackInQueue(e.id);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Row(
        children: [
          if (e.cover != null) ClipRRect(borderRadius: BorderRadius.circular(6), child: Image.network(e.cover!, width: 36, height: 36, fit: BoxFit.cover)),
          const SizedBox(width: 10),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(e.title, maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 14)), Text(e.artist, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(fontSize: 11, color: Theme.of(context).colorScheme.onSurfaceVariant))])),
          IconButton(iconSize: 17, icon: Icon(inQueue ? Icons.check_circle : Icons.add_circle_outline, color: inQueue ? Theme.of(context).colorScheme.primary : null), onPressed: () => _toggleTrackInQueue(c, e)),
          IconButton(iconSize: 18, icon: const Icon(Icons.favorite, color: Colors.redAccent), onPressed: () => _softRemove(c, e)),
        ],
      ),
    );
  }

  void _softRemove(PlayerController c, FavoriteEntry e) {
    c.setPendingRemove(e, true);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: const Text('Removed. Tap UNDO to restore.'),
      action: SnackBarAction(label: 'UNDO', onPressed: () => c.setPendingRemove(e, false)),
    ));
  }

  Widget _queueToggle(PlayerController c, QueueState state, {required VoidCallback onTap}) {
    final scheme = Theme.of(context).colorScheme;
    final IconData icon;
    final Color? color;
    switch (state) {
      case QueueState.full:
        icon = Icons.check_circle;
        color = scheme.primary;
      case QueueState.partial:
        icon = Icons.check_circle_outline;
        color = scheme.primary.withValues(alpha: 0.6);
      case QueueState.none:
        icon = Icons.add_circle_outline;
        color = null;
    }
    return IconButton(iconSize: 20, icon: Icon(icon, color: color), onPressed: onTap);
  }

  Future<void> _toggleAlbumInQueue(PlayerController c, FavoriteEntry e) async {
    final state = c.albumQueueState(e);
    if (state == QueueState.full) {
      c.removeAlbumFromQueue('album/${e.id}');
      return;
    }
    try {
      List<MobileTrack> tracks;
      if (e.tracks != null && e.tracks!.isNotEmpty) {
        // 用缓存曲目逐首解析(保持排除语义)
        tracks = [];
        for (final t in e.tracks!) {
          if (!e.excluded.contains(t.id)) tracks.add(await ApiClient.instance.stream(t.id));
        }
      } else {
        tracks = await ApiClient.instance.resolve(['album/${e.id}']);
        c.updateAlbumTracks(e, tracks.map((m) => QueueTrack.fromMobile(m, sourceType: 'album', sourceKey: 'album/${e.id}')).toList());
      }
      if (mounted) c.addAlbumTracks(tracks);
    } catch (err) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$err')));
    }
  }

  Future<void> _downloadAlbum(PlayerController c, String albumId, String albumTitle) async {
    final id = albumId.isNotEmpty ? albumId : albumTitle;
    final messenger = ScaffoldMessenger.maybeOf(context);
    try {
      final tracks = await ApiClient.instance.resolve(['album/$id']);
      if (!mounted || tracks.isEmpty) {
        messenger?.showSnackBar(const SnackBar(content: Text('No tracks to download.')));
        return;
      }
      await DownloadsScreen.downloadMany(context, tracks);
    } catch (err) {
      messenger?.showSnackBar(SnackBar(content: Text('Download failed: $err')));
    }
  }

  Future<void> _toggleTrackInQueue(PlayerController c, FavoriteEntry e) async {
    if (c.trackInQueue(e.id)) {
      final idx = c.queue.indexWhere((t) => t.id == e.id);
      if (idx >= 0) c.removeFromQueue(idx);
      return;
    }
    try {
      final t = await ApiClient.instance.stream(e.id);
      if (mounted) c.addTrack(t);
    } catch (err) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$err')));
    }
  }

  // ---- 艺术家 Tab(关注并入) ----
  Widget _artistTab(PlayerController c) {
    if (c.follows.isEmpty) {
      return const _EmptyState(icon: Icons.person_add, text: 'Artists you follow will appear here\nSearch an artist and follow them');
    }
    return ListView.builder(
      padding: const EdgeInsets.only(bottom: 60),
      itemCount: c.follows.length,
      itemBuilder: (_, i) {
        final a = c.follows[i];
        return ListTile(
          leading: a.picture != null ? ClipRRect(borderRadius: BorderRadius.circular(20), child: Image.network(a.picture!, width: 36, height: 36, fit: BoxFit.cover)) : const CircleAvatar(child: Icon(Icons.person)),
          title: Text(a.name),
          trailing: IconButton(icon: const Icon(Icons.person_remove_outlined), onPressed: () => c.toggleFollowArtist(a.id, a.name, picture: a.picture)),
          onTap: () {
            Navigator.of(context).push(MaterialPageRoute(builder: (_) => ArtistDetailScreen(artistId: a.id, initialName: a.name)));
          },
        );
      },
    );
  }
}

class _QueueGroup {
  final String key;
  final String type;
  final List<(QueueTrack, int)> items;
  _QueueGroup({required this.key, required this.type, required this.items});
}

class _EmptyState extends StatelessWidget {
  final IconData icon;
  final String text;
  const _EmptyState({required this.icon, required this.text});
  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 40, color: Theme.of(context).colorScheme.onSurfaceVariant.withValues(alpha: 0.5)),
          const SizedBox(height: 8),
          Text(text, style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
        ],
      ),
    );
  }
}
