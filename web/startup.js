(function () {
  'use strict';
  var completed = false;
  var timer;
  var started = new Date().toISOString();
  var reason = '';
  function diagnose() {
    var report = {
      app: 'HomePlan', started: started, browser: navigator.userAgent,
      web: !!window.HOMEPLAN_BROWSER,
      javascriptModules: 'noModule' in document.createElement('script'),
      structuredClone: typeof window.structuredClone === 'function',
      dialog: !!(window.HTMLDialogElement && HTMLDialogElement.prototype.showModal),
      error: reason
    };
    var url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], {type:'application/json'}));
    var a = document.createElement('a');a.href = url;a.download = 'homeplan-diagnostics.json';a.click();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }
  function fail(message) {
    if (completed) return;
    completed = true;clearTimeout(timer);reason = String(message).slice(0, 1200);
    var content = document.getElementById('content');if (!content) return;
    content.innerHTML = '<section class="card"><h2>앱 준비가 완료되지 않았습니다.</h2><p id="startup-error"></p><p>다시 시도해도 같으면 최신 Edge 또는 Chrome에서 열어주세요. 진단 파일에는 브라우저 정보와 오류만 담고 금융 입력은 담지 않습니다.</p><button class="button primary" id="startup-retry">다시 시도</button> <button class="button" id="startup-report">진단 파일 저장</button></section>';
    document.getElementById('startup-error').textContent = reason;
    document.getElementById('startup-retry').onclick = function () { location.reload(); };
    document.getElementById('startup-report').onclick = diagnose;
  }
  function wait(milliseconds) {clearTimeout(timer);timer = setTimeout(function () {fail('준비 시간이 초과되었습니다. 연결 또는 브라우저의 실행 제한을 확인해 주세요.');}, milliseconds);}
  window.homeplanStartup = {
    done: function () { completed = true;clearTimeout(timer); },
    wait: wait, fail: fail
  };
  window.addEventListener('error', function (event) {
    if (event.target && event.target.tagName === 'SCRIPT') fail('화면 스크립트를 불러오지 못했습니다.');
    else if (event.message) fail(event.message);
  }, true);
  window.addEventListener('unhandledrejection', function (event) {fail(event.reason && event.reason.message || '초기 실행 중 오류가 발생했습니다.');});
  wait(45000);
}());
