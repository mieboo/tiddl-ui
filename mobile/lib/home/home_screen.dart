import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../auth/auth_controller.dart';
import '../state/player_controller.dart';
import 'left_panel.dart';
import 'now_panel.dart';
import 'right_panel.dart';

/// 三栏横滑壳:PageView(左队列 / 中播放 / 右歌词)。
/// 中间(now)为锚点;左↔中↔右往返,不允许左↔右直接跳穿。
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});
  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final PageController _pageController = PageController(initialPage: 1);
  int _page = 1;

  void _goto(int target) {
    _pageController.animateToPage(target, duration: const Duration(milliseconds: 260), curve: Curves.easeOutCubic);
  }

  @override
  Widget build(BuildContext context) {
    final controller = context.read<PlayerController>();
    return Scaffold(
      body: Stack(
        children: [
          PageView(
            controller: _pageController,
            onPageChanged: (i) => setState(() => _page = i),
            children: const [
              LeftPanel(),
              NowPanel(),
              RightPanel(),
            ],
          ),
          // 返回播放锚点悬浮球(在左/右栏时显示)
          Positioned(
            right: 16,
            bottom: 24,
            child: _page == 1
                ? const SizedBox.shrink()
                : FloatingActionButton.small(
                    heroTag: 'back-to-now',
                    tooltip: 'Back to player',
                    onPressed: () => _goto(1),
                    child: const Icon(Icons.play_arrow),
                  ),
          ),
          // 底部指示器:左-中-右
          Positioned(
            left: 0,
            right: 0,
            bottom: 10,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _dot(_page == 0),
                const SizedBox(width: 6),
                _dot(_page == 1),
                const SizedBox(width: 6),
                _dot(_page == 2),
              ],
            ),
          ),
          Positioned(
            top: MediaQuery.of(context).padding.top + 4,
            right: 12,
            child: IconButton(
              icon: const Icon(Icons.logout),
              tooltip: 'Sign out',
              onPressed: () async {
                await controller.persist();
                if (context.mounted) context.read<AuthController>().logout();
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _dot(bool active) => AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: active ? 18 : 6,
        height: 6,
        decoration: BoxDecoration(
          color: active ? Theme.of(context).colorScheme.primary : Theme.of(context).colorScheme.onSurfaceVariant.withValues(alpha: 0.4),
          borderRadius: BorderRadius.circular(3),
        ),
      );
}
