/* Public content only: no discovery, research or demonstration loader. */
(() => {
  const fail = () => { document.querySelector('#main').textContent = '内容暂时未能加载，请稍后重试。'; };
  const data = document.createElement('script');
  data.src = 'real-data.js?v=24c55aa0f7e0a95d';
  data.onerror = fail;
  data.onload = () => {
    const app = document.createElement('script');
    app.src = 'app.js?v=24c55aa0f7e0a95d';
    app.onerror = fail;
    document.head.append(app);
  };
  document.head.append(data);
})();
