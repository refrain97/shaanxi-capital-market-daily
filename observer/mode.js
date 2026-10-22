/* Public content only: no discovery, research or demonstration loader. */
(() => {
  const fail = () => { document.querySelector('#main').textContent = '内容暂时未能加载，请稍后重试。'; };
  const data = document.createElement('script');
  data.src = 'real-data.js?v=c78d5ebaa3f4ae4b';
  data.onerror = fail;
  data.onload = () => {
    const app = document.createElement('script');
    app.src = 'app.js?v=c78d5ebaa3f4ae4b';
    app.onerror = fail;
    document.head.append(app);
  };
  document.head.append(data);
})();
