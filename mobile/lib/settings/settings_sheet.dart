import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../auth/auth_controller.dart';
import '../core/api_client.dart';
import '../core/config.dart';

/// 设置底部面板:服务器地址 / 默认音质 / 账号 / 登出。
class SettingsSheet extends StatefulWidget {
  const SettingsSheet({super.key});
  @override
  State<SettingsSheet> createState() => _SettingsSheetState();
}

class _SettingsSheetState extends State<SettingsSheet> {
  String _quality = 'high';

  @override
  void initState() {
    super.initState();
  }

  Future<void> _editServer() async {
    final ctrl = TextEditingController(text: AppConfig.baseUrl);
    final url = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Server address'),
        content: TextField(controller: ctrl, decoration: const InputDecoration(hintText: 'http://192.168.1.10:8765')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, ctrl.text), child: const Text('Save')),
        ],
      ),
    );
    if (url != null && url.trim().isNotEmpty) {
      await AppConfig.setBaseUrl(url.trim());
      if (mounted) setState(() {});
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = ApiClient.instance.user;
    return SafeArea(
      child: ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
        children: [
          if (user != null) ...[
            ListTile(
              leading: const CircleAvatar(child: Icon(Icons.person)),
              title: Text(user.username),
              subtitle: Text(user.isAdmin ? 'Administrator' : 'User'),
            ),
            const Divider(),
          ],
          ListTile(
            leading: const Icon(Icons.dns),
            title: const Text('Server'),
            subtitle: Text(AppConfig.baseUrl, maxLines: 1, overflow: TextOverflow.ellipsis),
            onTap: _editServer,
          ),
          ListTile(
            leading: const Icon(Icons.high_quality),
            title: const Text('Default quality'),
            trailing: DropdownButton<String>(
              value: _quality,
              underline: const SizedBox.shrink(),
              items: const [
                DropdownMenuItem(value: 'low', child: Text('LOW')),
                DropdownMenuItem(value: 'normal', child: Text('HIGH')),
                DropdownMenuItem(value: 'high', child: Text('LOSSLESS')),
                DropdownMenuItem(value: 'max', child: Text('HI-RES')),
              ],
              onChanged: (v) => setState(() => _quality = v ?? 'high'),
            ),
          ),
          const ListTile(
            leading: Icon(Icons.info_outline),
            title: Text('Client'),
            subtitle: Text('ATP Mobile v0.1.0 · v1 API · zero server bandwidth'),
          ),
          const Divider(),
          ListTile(
            leading: Icon(Icons.logout, color: Theme.of(context).colorScheme.error),
            title: Text('Sign out', style: TextStyle(color: Theme.of(context).colorScheme.error)),
            onTap: () {
              Navigator.pop(context);
              context.read<AuthController>().logout();
            },
          ),
        ],
      ),
    );
  }
}
