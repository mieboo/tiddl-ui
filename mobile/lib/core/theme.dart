import 'package:flutter/material.dart';

/// 主题:复刻网页版设计语言(深/浅色)。
class AppTheme {
  AppTheme._();

  static const Color accent = Color(0xFF00C2FF);
  static const Color danger = Color(0xFFE5484D);
  static const Color warning = Color(0xFFE5A00D);

  static ThemeData dark() => ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0B0C0E),
        colorScheme: const ColorScheme.dark(
          primary: accent,
          surface: Color(0xFF141619),
          surfaceContainerHighest: Color(0xFF1C1F23),
          onSurface: Color(0xFFE8E8E8),
          onSurfaceVariant: Color(0xFF9A9A9A),
          error: danger,
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF0B0C0E),
          elevation: 0,
          centerTitle: false,
        ),
        dividerTheme: const DividerThemeData(color: Color(0xFF2A2E33)),
        cardTheme: CardThemeData(
          color: const Color(0xFF141619),
          elevation: 0,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      );

  static ThemeData light() => ThemeData(
        brightness: Brightness.light,
        scaffoldBackgroundColor: Colors.white,
        colorScheme: const ColorScheme.light(
          primary: Color(0xFF0078A8),
          surface: Colors.white,
          surfaceContainerHighest: Color(0xFFEDF0F1),
          onSurface: Color(0xFF1A1A1A),
          onSurfaceVariant: Color(0xFF6B6B6B),
          error: danger,
        ),
        appBarTheme: const AppBarTheme(backgroundColor: Colors.white, elevation: 0),
        dividerTheme: const DividerThemeData(color: Color(0xFFE2E6E8)),
        cardTheme: CardThemeData(
          color: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      );
}
