import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:webview_flutter_android/webview_flutter_android.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:file_picker/file_picker.dart';

const String kAppUrl = String.fromEnvironment(
  'APP_URL',
  defaultValue: 'https://bitcoiners.life',
);

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
  runApp(const BitcoinersApp());
}

class BitcoinersApp extends StatelessWidget {
  const BitcoinersApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Bitcoiners',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFF7931A),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: const WebViewPage(),
    );
  }
}

class WebViewPage extends StatefulWidget {
  const WebViewPage({super.key});

  @override
  State<WebViewPage> createState() => _WebViewPageState();
}

class _WebViewPageState extends State<WebViewPage> {
  late final WebViewController _controller;
  bool _isLoading = true;
  bool _hasError = false;
  Timer? _loadTimeout;
  late final StreamSubscription<List<ConnectivityResult>> _connectivitySub;

  void _log(String msg) => debugPrint('[Bitcoiners] $msg');

  @override
  void initState() {
    super.initState();
    _initWebView();
    WidgetsBinding.instance.addPostFrameCallback((_) => _requestPermissions());
    _connectivitySub = Connectivity().onConnectivityChanged.listen((results) {
      final hasConnection = results.any((r) => r != ConnectivityResult.none);
      if (hasConnection && _hasError) {
        _reload();
      }
    });
  }

  Future<void> _requestPermissions() async {
    await [
      Permission.camera,
      Permission.photos,
      Permission.videos,
    ].request();
  }

  void _startLoadTimeout() {
    _loadTimeout?.cancel();
    _loadTimeout = Timer(const Duration(seconds: 30), () {
      if (mounted && _isLoading) {
        setState(() {
          _isLoading = false;
          _hasError = true;
        });
      }
    });
  }

  void _initWebView() {
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setUserAgent(
        'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
      )
      ..setBackgroundColor(const Color(0xFF0A0A0A))
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (url) {
            _log('페이지 로딩: $url');
            setState(() {
              _isLoading = true;
              _hasError = false;
            });
            _startLoadTimeout();
          },
          onPageFinished: (url) {
            _loadTimeout?.cancel();
            _log('페이지 완료: $url');
            setState(() => _isLoading = false);
          },
          onWebResourceError: (error) {
            _log('WebView 에러: ${error.description} (code=${error.errorCode}, mainFrame=${error.isForMainFrame})');
            if (error.isForMainFrame != false) {
              _loadTimeout?.cancel();
              setState(() {
                _isLoading = false;
                _hasError = true;
              });
            }
          },
          onNavigationRequest: (request) {
            _log('네비게이션: ${request.url}');
            return NavigationDecision.navigate;
          },
        ),
      )
      ..setOnConsoleMessage((msg) => _log('[JS] ${msg.message}'));

    // Android: WebView 내에서 웹이 카메라 등 권한 요청 시 자동 허용
    // 그리고 파일/영상 업로드 처리 (WebView 기본은 무시함)
    if (_controller.platform is AndroidWebViewController) {
      final androidCtrl = _controller.platform as AndroidWebViewController;

      androidCtrl.setOnPlatformPermissionRequest((request) {
        request.grant();
      });

      androidCtrl.setOnShowFileSelector((FileSelectorParams params) async {
        try {
          _log('파일선택 요청: accept=${params.acceptTypes}');
          FileType fileType = FileType.any;
          final accept = params.acceptTypes;

          if (accept.any((t) => t.startsWith('video/'))) {
            fileType = FileType.video;
          } else if (accept.any((t) => t.startsWith('image/'))) {
            fileType = FileType.image;
          } else if (accept.any((t) => t.startsWith('audio/'))) {
            fileType = FileType.audio;
          }
          _log('파일타입: $fileType');

          final result = await FilePicker.platform.pickFiles(
            type: fileType,
            allowMultiple: false,
          );

          if (result == null || result.paths.isEmpty) {
            _log('파일선택 취소 또는 실패');
            return [];
          }
          final uris = result.paths
              .whereType<String>()
              .map((p) => Uri.file(p).toString())
              .toList();
          _log('파일선택 완료: $uris');
          return uris;
        } catch (e, st) {
          _log('파일선택 예외: $e\n$st');
          return [];
        }
      });
    }

    _controller.loadRequest(Uri.parse(kAppUrl));
    _startLoadTimeout();
  }

  void _reload() {
    setState(() {
      _isLoading = true;
      _hasError = false;
    });
    _controller.loadRequest(Uri.parse(kAppUrl));
    _startLoadTimeout();
  }

  @override
  void dispose() {
    _loadTimeout?.cancel();
    _connectivitySub.cancel();
    super.dispose();
  }

  void _showStatusSheet() {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1A1A1A),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (_) => const _StatusSheet(),
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      onPopInvoked: (didPop) async {
        if (didPop) return;
        if (await _controller.canGoBack()) {
          await _controller.goBack();
        }
      },
      child: Scaffold(
        backgroundColor: const Color(0xFF0A0A0A),
        body: Stack(
          children: [
            if (!_hasError) WebViewWidget(controller: _controller),
            if (_isLoading && !_hasError)
              const Center(
                child: CircularProgressIndicator(color: Color(0xFFF7931A)),
              ),
            if (_hasError) _buildErrorView(),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorView() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.wifi_off, size: 64, color: Color(0xFF666666)),
            const SizedBox(height: 16),
            const Text(
              '연결할 수 없습니다',
              style: TextStyle(
                color: Colors.white,
                fontSize: 20,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              '인터넷 연결을 확인하고 다시 시도해주세요',
              style: TextStyle(color: Color(0xFF888888), fontSize: 14),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 32),
            ElevatedButton(
              onPressed: _reload,
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFFF7931A),
                foregroundColor: Colors.black,
                padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 12),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
              ),
              child: const Text('다시 시도', style: TextStyle(fontWeight: FontWeight.bold)),
            ),
            const SizedBox(height: 12),
            TextButton(
              onPressed: _showStatusSheet,
              child: const Text(
                '권한 및 연결 상태 확인',
                style: TextStyle(color: Color(0xFF888888)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusSheet extends StatefulWidget {
  const _StatusSheet();

  @override
  State<_StatusSheet> createState() => _StatusSheetState();
}

class _StatusSheetState extends State<_StatusSheet> {
  Map<String, String> _permissionStatus = {};
  String _connectivity = '확인 중...';
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadStatus();
  }

  Future<void> _loadStatus() async {
    final results = await Connectivity().checkConnectivity();
    final hasNet = results.any((r) => r != ConnectivityResult.none);

    final camera = await Permission.camera.status;
    final photos = await Permission.photos.status;
    final videos = await Permission.videos.status;

    if (!mounted) return;
    setState(() {
      _connectivity = hasNet ? '연결됨' : '연결 안됨';
      _permissionStatus = {
        '인터넷': '자동 허용',
        '카메라': _statusLabel(camera),
        '사진/미디어': _statusLabel(photos),
        '동영상': _statusLabel(videos),
      };
      _loading = false;
    });
  }

  String _statusLabel(PermissionStatus s) {
    switch (s) {
      case PermissionStatus.granted:
        return '허용됨';
      case PermissionStatus.denied:
        return '거부됨';
      case PermissionStatus.permanentlyDenied:
        return '영구 거부 (설정에서 변경 필요)';
      case PermissionStatus.restricted:
        return '제한됨';
      default:
        return '요청 안됨';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '앱 상태',
            style: TextStyle(
              color: Colors.white,
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            '서버: $kAppUrl',
            style: const TextStyle(color: Color(0xFF888888), fontSize: 12),
          ),
          const SizedBox(height: 16),
          if (_loading)
            const Center(child: CircularProgressIndicator(color: Color(0xFFF7931A)))
          else ...[
            _StatusRow(label: '네트워크', value: _connectivity,
                isOk: _connectivity == '연결됨'),
            const Divider(color: Color(0xFF333333), height: 24),
            const Text(
              '권한 상태',
              style: TextStyle(color: Color(0xFF888888), fontSize: 12),
            ),
            const SizedBox(height: 8),
            ..._permissionStatus.entries.map(
              (e) => _StatusRow(
                label: e.key,
                value: e.value,
                isOk: e.value == '허용됨' || e.value == '자동 허용',
              ),
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton(
                onPressed: () async {
                  await [
                    Permission.camera,
                    Permission.photos,
                    Permission.videos,
                  ].request();
                  await _loadStatus();
                },
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: Color(0xFFF7931A)),
                  foregroundColor: const Color(0xFFF7931A),
                ),
                child: const Text('권한 다시 요청'),
              ),
            ),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton(
                onPressed: () => openAppSettings(),
                style: OutlinedButton.styleFrom(
                  side: const BorderSide(color: Color(0xFF555555)),
                  foregroundColor: const Color(0xFF888888),
                ),
                child: const Text('Android 앱 권한 설정 열기'),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _StatusRow extends StatelessWidget {
  final String label;
  final String value;
  final bool isOk;

  const _StatusRow({required this.label, required this.value, required this.isOk});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: const TextStyle(color: Colors.white, fontSize: 14)),
          Row(
            children: [
              Icon(
                isOk ? Icons.check_circle : Icons.cancel,
                size: 14,
                color: isOk ? Colors.green : Colors.red,
              ),
              const SizedBox(width: 4),
              Text(
                value,
                style: TextStyle(
                  color: isOk ? Colors.green : Colors.red,
                  fontSize: 14,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
