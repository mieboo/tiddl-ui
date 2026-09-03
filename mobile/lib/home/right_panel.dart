import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../downloads/downloads_screen.dart';
import '../models/library.dart';
import '../state/player_controller.dart';

/// 右栏(从右往左滑打开):信息 / 下载器。
class RightPanel extends StatefulWidget {
  const RightPanel({super.key});
  @override
  State<RightPanel> createState() => _RightPanelState();
}

class _RightPanelState extends State<RightPanel> {
  String _tab = 'info'; // info | downloader

  @override
  Widget build(BuildContext context) {
    final c = context.watch<PlayerController>();
    final t = c.current >= 0 && c.current < c.queue.length ? c.queue[c.current] : null;
    return SafeArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
            child: Row(
              children: [
                _tabBtn('info', 'Info'),
                _tabBtn('downloader', 'Downloader'),
              ],
            ),
          ),
          Expanded(
            child: _tab == 'downloader' ? const DownloadsScreen() : _info(t),
          ),
        ],
      ),
    );
  }

  Widget _tabBtn(String key, String label) {
    final active = _tab == key;
    return Expanded(
      child: InkWell(
        onTap: () => setState(() => _tab = key),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12),
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

  Widget _info(QueueTrack? t) {
    final muted = Theme.of(context).colorScheme.onSurfaceVariant;
    if (t == null) {
      return Center(child: Text('Play a track to see its details here', style: TextStyle(color: muted)));
    }
    Widget row(String label, String value) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 8),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(width: 90, child: Text(label, style: TextStyle(color: muted, fontSize: 13))),
              Expanded(child: Text(value, style: const TextStyle(fontSize: 13))),
            ],
          ),
        );
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        if (t.cover != null)
          ClipRRect(borderRadius: BorderRadius.circular(10), child: Image.network(t.cover!, width: 120, height: 120, fit: BoxFit.cover, errorBuilder: (_, __, ___) => const SizedBox.shrink())),
        if (t.cover != null) const SizedBox(height: 12),
        row('Title', t.title),
        row('Artist', t.artist),
        row('Album', t.album),
        if (t.duration != null) row('Duration', _fmt(Duration(seconds: t.duration!))),
      ],
    );
  }

  String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final s = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '${d.inMinutes}:$m:$s';
  }
}
