import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/config.dart';
import 'auth_controller.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _user = TextEditingController();
  final _pass = TextEditingController();
  final _totp = TextEditingController();
  bool _showTotp = false;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthController>();
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 360),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text('ATP Mobile', textAlign: TextAlign.center, style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
                const SizedBox(height: 4),
                Text('Abducted Tidal Player', textAlign: TextAlign.center, style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
                const SizedBox(height: 24),
                TextField(controller: _user, decoration: const InputDecoration(labelText: 'Username', border: OutlineInputBorder())),
                const SizedBox(height: 12),
                TextField(controller: _pass, obscureText: true, decoration: const InputDecoration(labelText: 'Password', border: OutlineInputBorder())),
                if (_showTotp) ...[
                  const SizedBox(height: 12),
                  TextField(controller: _totp, keyboardType: TextInputType.number, maxLength: 6, decoration: const InputDecoration(labelText: '2FA code', border: OutlineInputBorder())),
                ],
                if (auth.error != null) ...[
                  const SizedBox(height: 12),
                  Text(auth.error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                ],
                const SizedBox(height: 20),
                FilledButton(
                  onPressed: auth.busy ? null : () async {
                    final ok = await auth.login(_user.text.trim(), _pass.text, totp: _totp.text.trim().isEmpty ? null : _totp.text.trim());
                    // 服务端提示 2FA 时显示 TOTP 输入框
                    if (!ok && !_showTotp && RegExp(r'two-factor|2fa|code', caseSensitive: false).hasMatch(auth.error ?? '')) {
                      setState(() => _showTotp = true);
                    }
                  },
                  child: Text(auth.busy ? 'Signing in…' : 'Sign in'),
                ),
                const SizedBox(height: 8),
                TextButton(
                  onPressed: _editServer,
                  child: Text('Server: ${AppConfig.baseUrl}', style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
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
      setState(() {});
    }
  }
}
