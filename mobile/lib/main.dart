import 'package:flutter/material.dart';
import 'package:media_kit/media_kit.dart';
import 'package:provider/provider.dart';
import 'core/config.dart';
import 'core/api_client.dart';
import 'core/theme.dart';
import 'auth/auth_controller.dart';
import 'auth/login_screen.dart';
import 'home/home_screen.dart';
import 'state/player_controller.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  MediaKit.ensureInitialized();
  await AppConfig.load();
  final auth = AuthController(ApiClient.instance);
  await auth.restore();
  final player = PlayerController(ApiClient.instance);
  await player.load();
  runApp(TiddlApp(auth: auth, player: player));
}

class TiddlApp extends StatelessWidget {
  final AuthController auth;
  final PlayerController player;
  const TiddlApp({super.key, required this.auth, required this.player});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: auth),
        ChangeNotifierProvider.value(value: player),
      ],
      child: Consumer<AuthController>(
        builder: (context, auth, _) {
          return MaterialApp(
            title: 'ATP Mobile',
            debugShowCheckedModeBanner: false,
            theme: AppTheme.dark(),
            darkTheme: AppTheme.dark(),
            themeMode: ThemeMode.dark,
            home: auth.isLoggedIn ? const HomeScreen() : const LoginScreen(),
          );
        },
      ),
    );
  }
}
