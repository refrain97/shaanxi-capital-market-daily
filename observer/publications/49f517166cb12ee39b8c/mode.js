/* Public content only: no discovery, research or demonstration loader. */
(() => {
  const fail = () => { document.querySelector('#main').textContent = '内容暂时未能加载，请稍后重试。'; };
  const data = document.createElement('script');
  data.src = 'real-data.js?v=6c4a8221cf80d1d4';
  data.onerror = fail;
  data.onload = () => {
    const app = document.createElement('script');
    app.src = 'app.js?v=6c4a8221cf80d1d4';
    app.onerror = fail;
    document.head.append(app);
  };
  document.head.append(data);
})();
