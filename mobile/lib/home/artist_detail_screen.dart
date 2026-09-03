import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/api_client.dart';
import '../models/library.dart';
import '../state/player_controller.dart';

/// 艺术家详情页:专辑 / 单曲 / 参与曲目,均带"加入队列"能力。
class ArtistDetailScreen extends StatefulWidget {
  final String artistId;
  final String? initialName;
  const ArtistDetailScreen({super.key, required this.artistId, this.initialName});
  @override
  State<ArtistDetailScreen> createState() => _ArtistDetailScreenState();
}

class _ArtistDetailScreenState extends State<ArtistDetailScreen> {
  ArtistDetail? _detail;
  bool _loading = true;
  String? _error;
  String _section = 'albums'; // albums | singles | tracks

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final d = await ApiClient.instance.artist(widget.artistId);
      if (mounted) setState(() => _detail = d);
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_detail?.name ?? widget.initialName ?? 'Artist')),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: CircularProgressIndicator(strokeWidth: 2));
    if (_error != null) {
      return Center(child: Padding(padding: const EdgeInsets.all(20), child: Text(_error!, textAlign: TextAlign.center)));
    }
    final d = _detail!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              if (d.picture != null)
                ClipRRect(borderRadius: BorderRadius.circular(8), child: Image.network(d.picture!, width: 64, height: 64, fit: BoxFit.cover))
              else
                Container(width: 64, height: 64, decoration: BoxDecoration(borderRadius: BorderRadius.circular(8), color: Theme.of(context).colorScheme.surfaceContainerHighest), child: const Icon(Icons.person)),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(d.name, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
                    Text('${d.albums.length} albums · ${d.singles.length} singles', style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
                  ],
                ),
              ),
              _FollowButton(artistId: d.id, name: d.name, picture: d.picture),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Row(
            children: [
              _seg('albums', 'Albums'),
              _seg('singles', 'Singles'),
              if (d.tracks.isNotEmpty) _seg('tracks', 'Tracks'),
            ],
          ),
        ),
        const Divider(height: 1),
        Expanded(child: _listFor(d)),
      ],
    );
  }

  Widget _seg(String key, String label) {
    final active = _section == key;
    return Expanded(
      child: InkWell(
        onTap: () => setState(() => _section = key),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: active ? Theme.of(context).colorScheme.primary : Colors.transparent, width: 2)),
          ),
          child: Center(
            child: Text(label, style: TextStyle(fontWeight: active ? FontWeight.w600 : FontWeight.w400, color: active ? Theme.of(context).colorScheme.primary : Theme.of(context).colorScheme.onSurfaceVariant)),
          ),
        ),
      ),
    );
  }

  Widget _listFor(ArtistDetail d) {
    if (_section == 'albums') {
      final items = [...d.albums, ...d.singles];
      if (items.isEmpty) return const _ArtistEmpty(icon: Icons.album, text: 'No albums');
      return ListView.builder(
        itemCount: items.length,
        itemBuilder: (_, i) {
          final a = items[i];
          return ListTile(
            leading: a.cover != null ? ClipRRect(borderRadius: BorderRadius.circular(6), child: Image.network(a.cover!, width: 40, height: 40, fit: BoxFit.cover)) : const Icon(Icons.album),
            title: Text(a.title, maxLines: 1, overflow: TextOverflow.ellipsis),
            subtitle: Text('${a.year ?? ''}${a.trackCount > 0 ? ' · ${a.trackCount} tracks' : ''}'),
            trailing: _QueueToggleIcon(albumId: a.id, albumTitle: a.title, artist: d.name, cover: a.cover),
            onTap: () => _playAlbum(a.id),
          );
        },
      );
    }
    if (_section == 'singles') {
      // 单曲已在 albums 段展示(合并);这里作为备用空页
      return const _ArtistEmpty(icon: Icons.music_note, text: 'Shown under Albums');
    }
    final ts = d.tracks;
    if (ts.isEmpty) return const _ArtistEmpty(icon: Icons.music_note, text: 'No tracks');
    return ListView.builder(
      itemCount: ts.length,
      itemBuilder: (_, i) {
        final t = ts[i];
        return ListTile(
          dense: true,
          leading: const Icon(Icons.music_note, size: 20),
          title: Text(t.title, maxLines: 1, overflow: TextOverflow.ellipsis),
          subtitle: Text(t.album, maxLines: 1, overflow: TextOverflow.ellipsis),
          onTap: () => _playTrack(t.id),
        );
      },
    );
  }

  Future<void> _playAlbum(String albumId) async {
    final c = context.read<PlayerController>();
    try {
      final tracks = await ApiClient.instance.resolve(['album/$albumId']);
      if (mounted && tracks.isNotEmpty) c.addAlbumTracks(tracks);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  Future<void> _playTrack(String trackId) async {
    final c = context.read<PlayerController>();
    try {
      final t = await ApiClient.instance.stream(trackId);
      if (mounted) c.addTrack(t);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }
}

class _FollowButton extends StatelessWidget {
  final String artistId;
  final String name;
  final String? picture;
  const _FollowButton({required this.artistId, required this.name, this.picture});
  @override
  Widget build(BuildContext context) {
    final c = context.watch<PlayerController>();
    final following = c.isFollowing(artistId);
    return TextButton.icon(
      onPressed: () => c.toggleFollowArtist(artistId, name, picture: picture),
      icon: Icon(following ? Icons.check : Icons.add, size: 16),
      label: Text(following ? 'Following' : 'Follow'),
    );
  }
}

/// 专辑"加入队列"三态图标。
class _QueueToggleIcon extends StatelessWidget {
  final String albumId;
  final String albumTitle;
  final String artist;
  final String? cover;
  const _QueueToggleIcon({required this.albumId, required this.albumTitle, required this.artist, this.cover});
  @override
  Widget build(BuildContext context) {
    final c = context.watch<PlayerController>();
    final fav = FavoriteEntry(kind: 'album', id: albumId, title: albumTitle, artist: artist, cover: cover);
    final state = c.albumQueueState(fav);
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
    return IconButton(
      icon: Icon(icon, color: color, size: 20),
      onPressed: () => _toggle(context, c, fav),
    );
  }

  Future<void> _toggle(BuildContext context, PlayerController c, FavoriteEntry fav) async {
    final messenger = ScaffoldMessenger.maybeOf(context);
    try {
      if (c.albumQueueState(fav) == QueueState.full) {
        c.removeAlbumFromQueue('album/$albumId');
        return;
      }
      final tracks = await ApiClient.instance.resolve(['album/$albumId']);
      if (tracks.isNotEmpty) c.addAlbumTracks(tracks);
    } catch (e) {
      messenger?.showSnackBar(SnackBar(content: Text('$e')));
    }
  }
}

class _ArtistEmpty extends StatelessWidget {
  final IconData icon;
  final String text;
  const _ArtistEmpty({required this.icon, required this.text});
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
