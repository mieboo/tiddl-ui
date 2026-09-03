import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/api_client.dart';
import '../models/library.dart';
import '../state/player_controller.dart';

/// 中栏(网页版 now-panel):正在播放。点击封面切换歌词覆盖层(cover-lyrics)。
class NowPanel extends StatefulWidget {
  const NowPanel({super.key});
  @override
  State<NowPanel> createState() => _NowPanelState();
}

class _NowPanelState extends State<NowPanel> {
  String _lyricsFor = '';
  LyricsData? _lyricsData;
  bool _showLyrics = false;

  Future<void> _loadLyrics(String trackId) async {
    if (_lyricsFor == trackId) return;
    setState(() {
      _lyricsFor = trackId;
      _lyricsData = null;
      _showLyrics = false;
    });
    try {
      final data = await ApiClient.instance.lyrics(trackId);
      if (mounted && _lyricsFor == trackId) setState(() => _lyricsData = data);
    } catch (_) {
      // 歌词拉取失败静默
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = context.watch<PlayerController>();
    final t = c.current >= 0 && c.current < c.queue.length ? c.queue[c.current] : null;
    if (t != null && t.id != _lyricsFor) _loadLyrics(t.id);
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    return SafeArea(
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              GestureDetector(
                onTap: t != null && _lyricsData != null && !_lyricsData!.isEmpty ? () => setState(() => _showLyrics = !_showLyrics) : null,
                child: Stack(
                  children: [
                    t?.cover != null
                        ? ClipRRect(
                            borderRadius: BorderRadius.circular(16),
                            child: Image.network(t!.cover!, width: 240, height: 240, fit: BoxFit.cover, errorBuilder: (_, __, ___) => _placeholder()),
                          )
                        : _placeholder(),
                    if (_showLyrics && _lyricsData != null && !_lyricsData!.isEmpty)
                      Positioned.fill(
                        child: Container(
                          decoration: BoxDecoration(borderRadius: BorderRadius.circular(16), color: const Color(0xE6000000)),
                          padding: const EdgeInsets.all(16),
                          child: SingleChildScrollView(
                            child: Text(
                              _lyricsData!.lyrics,
                              textAlign: _lyricsData!.rtl ? TextAlign.right : TextAlign.center,
                              style: const TextStyle(fontSize: 13, height: 1.6, color: Colors.white),
                            ),
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
              Text(t?.title ?? 'Nothing playing', textAlign: TextAlign.center, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w600)),
              const SizedBox(height: 6),
              Text(t?.artist ?? '', textAlign: TextAlign.center, maxLines: 1, overflow: TextOverflow.ellipsis, style: TextStyle(color: muted)),
              const SizedBox(height: 8),
              if (t != null) _badges(t),
              const SizedBox(height: 20),
              _seekRow(c),
              _controls(c),
            ],
          ),
        ),
      ),
    );
  }

  Widget _placeholder() => Container(
        width: 240,
        height: 240,
        decoration: BoxDecoration(borderRadius: BorderRadius.circular(16), color: Theme.of(context).colorScheme.surfaceContainerHighest),
        child: const Icon(Icons.music_note, size: 80),
      );

  Widget _badges(QueueTrack t) {
    final scheme = Theme.of(context).colorScheme;
    Widget chip(String text, {bool accent = false}) => Container(
          margin: const EdgeInsets.symmetric(horizontal: 4),
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            color: accent ? scheme.primary.withValues(alpha: 0.15) : scheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(999),
          ),
          child: Text(text, style: TextStyle(fontSize: 12, color: accent ? scheme.primary : scheme.onSurfaceVariant)),
        );
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        if (t.album.isNotEmpty) chip(t.album, accent: true),
      ],
    );
  }

  Widget _seekRow(PlayerController c) {
    return StreamBuilder(
      stream: c.player.stream.position,
      builder: (_, pos) => StreamBuilder(
        stream: c.player.stream.duration,
        builder: (_, dur) {
          final p = pos.data ?? Duration.zero;
          final d = dur.data ?? Duration.zero;
          final durMs = d.inMilliseconds.toDouble();
          final posMs = p.inMilliseconds.toDouble().clamp(0.0, durMs).toDouble();
          return Column(
            children: [
              Slider(
                max: durMs < 1 ? 1.0 : durMs,
                value: posMs,
                onChanged: (v) => c.player.seek(Duration(milliseconds: v.round())),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(_fmt(p), style: const TextStyle(fontSize: 11)),
                    Text(_fmt(d), style: const TextStyle(fontSize: 11)),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _controls(PlayerController c) {
    return StreamBuilder(
      stream: c.player.stream.playing,
      builder: (_, snap) {
        final playing = snap.data ?? false;
        return Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            IconButton(iconSize: 26, icon: const Icon(Icons.shuffle), color: c.shuffle ? Theme.of(context).colorScheme.primary : null, onPressed: c.toggleShuffle),
            IconButton(iconSize: 36, icon: const Icon(Icons.skip_previous), onPressed: c.prev),
            IconButton(
              iconSize: 54,
              icon: Icon(playing ? Icons.pause_circle_filled : Icons.play_circle_filled),
              onPressed: () => playing ? c.player.pause() : c.player.play(),
            ),
            IconButton(iconSize: 36, icon: const Icon(Icons.skip_next), onPressed: c.next),
            IconButton(
              iconSize: 26,
              icon: Icon(c.repeat == 1 ? Icons.repeat : (c.repeat == 2 ? Icons.repeat_one : Icons.repeat)),
              color: c.repeat > 0 ? Theme.of(context).colorScheme.primary : null,
              onPressed: c.cycleRepeat,
            ),
          ],
        );
      },
    );
  }

  String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '${d.inMinutes}:$m:$s';
  }
}
