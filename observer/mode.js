/* Public content only: no discovery, research or demonstration loader. */
(() => {
  const fail = () => { document.querySelector('#main').textContent = '内容暂时未能加载，请稍后重试。'; };
  const data = document.createElement('script');
  data.src = 'real-data.js?v=8b567bb5e109980b';
  data.onerror = fail;
  data.onload = () => {
    const app = document.createElement('script');
    app.src = 'app.js?v=8b567bb5e109980b';
    app.onerror = fail;
    document.head.append(app);
  };
  document.head.append(data);
})();
