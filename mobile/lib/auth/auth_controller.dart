import 'package:flutter/foundation.dart';
import '../core/api_client.dart';

class AuthController extends ChangeNotifier {
  final ApiClient api;
  AuthController(this.api);

  bool _busy = false;
  String? _error;

  bool get busy => _busy;
  String? get error => _error;
  bool get isLoggedIn => api.isLoggedIn;

  Future<void> restore() async {
    await api.restore();
    notifyListeners();
  }

  Future<bool> login(String username, String password, {String? totp}) async {
    _busy = true;
    _error = null;
    notifyListeners();
    try {
      await api.login(username, password, totp: totp);
      _busy = false;
      notifyListeners();
      return true;
    } catch (e) {
      _busy = false;
      _error = e.toString();
      notifyListeners();
      return false;
    }
  }

  Future<void> logout() async {
    await api.logout();
    notifyListeners();
  }
}
