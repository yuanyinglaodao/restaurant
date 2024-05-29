from django.urls import path, re_path
from . import views

# 订单子路由
urlpatterns = [
    path('', views.OrderHome, name='OrderHome'),
    path('check', views.CheckUnpaidOrder),
    path('checkout', views.CheckOut),
    path('orders/', views.order_list, name='order_list'),  # 订单查询
    re_path(r'q(?P<order_id>[\d]+)', views.QueryOrder),   #正则表达式来匹配URL中的订单ID（[\d]+表示一个或多个数字）。views.QueryOrder是指向处理这个URL请求的视图函数的引用。
]
