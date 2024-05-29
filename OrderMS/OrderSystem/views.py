import datetime
import json

from django.contrib.auth.decorators import login_required
from django.db import connection
from django.db.models import Count
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum
from django.core.files.storage import FileSystemStorage


from . import forms
from .models import Food, Foodtype, Order, OrderItem, Staff, Staff_Table,  OrderHotFood



# 01餐位下单
@csrf_exempt
def OrderHome(request):
    #如果请求方法为GET，
    if request.method == "GET":
        foodList = Food.objects.all()  #则查询数据库中的食物列表，
        foodTypeList = Foodtype.objects.all()  #食物类型列表
        tableList = Staff_Table.objects.all()  #和餐桌列表
        hot_foods = Food.objects.annotate(num_sold=Count('orderitem')).order_by('-num_sold')[:3] # 热销菜品： 使用annotate和Count来计算每个食物的购买数量，并按数量降序排序，取前3个

        return render(   #将它们传递给模板OrderHome.html进行渲染。
            request,
            'OrderHome.html',
            {
                'foodList': foodList,
                'foodTypeList': foodTypeList,
                'tableList': tableList,
                'hot_foods': hot_foods,
            }
        )

    elif request.method == "POST":
        foodList = json.loads(request.POST.get('foodList'))  #从POST数据中获取食物列表，并将其解析为Python列表
        table_id = request.POST.get('table')   # 从POST数据中获取餐桌ID

        # 创建订单 填写基本信息
        new_order = Order(table_id=table_id, is_pay=False)  # 创建一个新的订单对象，设置餐桌ID和是否已支付为False
        staff_in_charge = Staff_Table.objects.get(pk=table_id).staff   # 获取当前餐桌的负责人
        new_order.staff = staff_in_charge  # 当前桌子的负责人
        new_order.save()   # 保存订单到数据库

        # 先 save 再获取 ID
        order_id = new_order.ID
        food_amount = 0
        total_price = 0

        for food in foodList:
            curFood = Food.objects.get(pk=food['id'])  # 从数据库中获取当前食物对象
            price = curFood.price  # 获取食物的价格
            sum_price = price * food['amount']  # 计算食物的总价
            curFood.amount -= food['amount']  # 更新食物的库存量
            curFood.save()  # 保存更新后的食物对象到数据库

            food_amount += food['amount']  # 累加订单的食物总数量
            total_price += sum_price  # 累加订单的总价

            OrderItem.objects.create(    #订单
                orderID=new_order,
                foodID=curFood,
                amount=food['amount'],
                sum_price=sum_price
            )
        # 订单的物品总数、总价
        new_order.food_amount = food_amount
        new_order.total_price = total_price
        new_order.save()

        return HttpResponse(json.dumps({  #返回一个包含订单ID的JSON响应。
            'order_id': order_id
        }))


# 02账单详情页
def QueryOrder(request, order_id):
    try:
        order = Order.objects.get(pk=order_id)
    except:
        return HttpResponse('无此订单！')

    foodList = Food.objects.filter(orderitem__orderID__ID=order_id)

    with connection.cursor() as cursor:  #连接查询
        SELECT_COL = 'OrderSystem_food.ID ID, OrderSystem_food.title title, OrderSystem_orderitem.amount amount'
        SELECT_COL += ', OrderSystem_orderitem.sum_price '
        SELECT_COL += ', OrderSystem_orderitem.start_cook_time '
        SELECT_COL += ', OrderSystem_orderitem.end_cook_time '
        SELECT_FROM = 'OrderSystem_food, OrderSystem_orderitem '
        SELECT_WHERE = 'OrderSystem_food.ID=OrderSystem_orderitem.foodID_id '
        SELECT_WHERE += ' and OrderSystem_orderitem.orderID_id={0}'.format(
            order_id)
        cursor.execute(
            f'select {SELECT_COL} from {SELECT_FROM} where {SELECT_WHERE}')
        foodJsonList = dictfetchall(cursor)

    return render(request, 'QueryOrder.html', {
        'order': order,
        'foodList': foodJsonList,
    })


# 03待结账页面
def CheckUnpaidOrder(request):
    # 查询当前未结账订单
    orderList = []
    with connection.cursor() as cursor:
        SELECT_COL = 'ID, create_time, table_id, total_price'
        SELECT_FROM = 'OrderSystem_order'
        SELECT_WHERE = 'is_pay=0'  # 0 false
        SELECT = f'select {SELECT_COL} from {SELECT_FROM} where {SELECT_WHERE}'
        cursor.execute(SELECT)
        orderList = dictfetchall(cursor)
        print(orderList)

    return render(request, 'CheckUnpaidOrder.html', {
        'orderList': orderList,
    })


# 04结账
@csrf_exempt
def CheckOut(request):
    if request.method == "POST":
        order_list = json.loads(request.POST.get('order_list'))
        print(order_list)
        for order_data in order_list:
            print(order_data)
            order_id = order_data['order_id']
            is_pay = order_data['is_pay']

            if is_pay:
                order = Order.objects.get(pk=order_id)
                if order.is_pay:
                    print("已经支付！")
                    return HttpResponse(json.dumps({
                        'status': 'ALREADY_PAY'
                    }))

                order.is_pay = True
                order.pay_time = datetime.datetime.now()
                order.save()
            else:
                return HttpResponse(json.dumps({
                    'status': 'NO_PAY'
                }))

        return HttpResponse(json.dumps({
            'status': 'OK'
        }))


# 05管理界面（管理员）
@login_required
def manage(request):
    staffList = Staff.objects.all()
    # (餐桌号 + 餐桌名字 + 负责人ID + 负责人姓名)
    tableInfoList = []
    with connection.cursor() as cursor:
        SELECT_COL = ' distinct {0}_staff_table.ID table_id '
        SELECT_COL += ', {0}_staff_table.name table_name '
        SELECT_COL += ', {0}_staff.ID staff_id '
        SELECT_COL += ', {0}_staff.name staff_name '
        SELECT_COL = SELECT_COL.format('OrderSystem')

        SELECT_FROM = '{0}_staff_table, {0}_staff '
        SELECT_FROM = SELECT_FROM.format('OrderSystem')

        SELECT_WHERE = '{0}_staff.ID = {0}_staff_table.staff_id '
        SELECT_WHERE = SELECT_WHERE.format('OrderSystem')

        SELECT_SQL = f'select {SELECT_COL} from {SELECT_FROM} where {SELECT_WHERE}'
        cursor.execute(SELECT_SQL)

        tableInfoList = dictfetchall(cursor)

    return render(request, 'manage.html', {
        'tableInfoList': tableInfoList,
        'staffList': staffList,
        'user': request.user,
    })


# 06 获取正在接受服务的餐位信息
@csrf_exempt
def getServingTableList(request):
    # (餐桌号 + 餐桌名字 + 负责人ID + 负责人姓名)
    servingTableList = []
    with connection.cursor() as cursor:
        SELECT_COL = 'distinct {0}_order.table_id table_id '
        SELECT_COL = SELECT_COL.format('OrderSystem')

        SELECT_FROM = '{0}_order '
        SELECT_FROM = SELECT_FROM.format('OrderSystem')

        SELECT_WHERE = '{0}_order.is_pay = 0 '  # false 0
        SELECT_WHERE = SELECT_WHERE.format('OrderSystem')

        SELECT_SQL = f'select {SELECT_COL} from {SELECT_FROM} where {SELECT_WHERE}'
        SELECT_SQL += 'order by table_id'
        cursor.execute(SELECT_SQL)

        servingTableInfoList = dictfetchall(cursor)
        for tableInfo in servingTableInfoList:
            servingTableList.append(tableInfo['table_id'])
    print(json.dumps(servingTableList))
    return HttpResponse(json.dumps({
        'servingTableList': servingTableList,
    }))


# 07后厨查看订单（接单或上菜）
@csrf_exempt
def getOrderItemList(request):
    if request.method == "POST":
        # 没有指定 order_id 就返回所有 order_item
        order_id = request.POST.get('order_id')
        print(order_id)
        with connection.cursor() as cursor:
            #  构建SELECT子句
            SELECT_COL = '{0}orderitem.orderID_id orderID_id '
            SELECT_COL += ',{0}order.table_id table_id '
            SELECT_COL += ',{0}orderitem.foodID_id foodID_id '
            SELECT_COL += ',{0}food.title food_name '
            SELECT_COL += ',{0}orderitem.amount food_amount '
            SELECT_COL += ',{0}orderitem.status status '
            SELECT_COL = SELECT_COL.format('OrderSystem_')

            # 构建FROM子句
            SELECT_FROM = '{0}orderitem, {0}food, {0}order '
            SELECT_FROM = SELECT_FROM.format('OrderSystem_')

            # 构建WHERE子句
            SELECT_WHERE = 'foodID_id = {0}food.ID '
            SELECT_WHERE += ' and {0}order.ID = orderID_id '
            SELECT_WHERE += ' and {0}order.is_pay = 0 '
            SELECT_WHERE += (' and orderID_id=' +
                             order_id) if order_id != None else ''
            SELECT_WHERE = SELECT_WHERE.format('OrderSystem_')

            # 构建完整的SQL查询
            SELECT_SQL = f'select {SELECT_COL} from {SELECT_FROM} where {SELECT_WHERE}'
            SELECT_SQL += 'order by table_id'

            print(SELECT_SQL)  #测试sql查询
            '''
            select 
                OrderSystem_orderitem.orderID_id orderID_id ,
                OrderSystem_order.table_id table_id ,
                OrderSystem_orderitem.foodID_id foodID_id,
                OrderSystem_food.title food_name ,
                OrderSystem_orderitem.amount food_amount ,
                OrderSystem_orderitem.status status 
            from 
                OrderSystem_orderitem, OrderSystem_food, OrderSystem_order  
            where 
                foodID_id = OrderSystem_food.ID and OrderSystem_order.ID = orderID_id  and OrderSystem_order.is_pay = 0 order by table_id
            '''
            # 执行sql语句
            cursor.execute(SELECT_SQL)

            orderItemList = dictfetchall(cursor)
            # 将结果转换为JSON字符串
            json_data = json.dumps(orderItemList)
            print(json_data)
            return HttpResponse(json_data)


# 08更新餐桌表中的员工
@csrf_exempt
def set_staff_charge_table(request):
    if request.method == "POST":
        table_id = request.POST.get("table_id")
        staff_id = request.POST.get("staff_id")
        try:
            Staff_Table.objects.filter(pk=table_id).update(staff_id=staff_id)
            return HttpResponse(json.dumps({
                'status': "OK"
            }))
        except:
            return HttpResponse(json.dumps({
                'status': "FAIL"
            }))


# 09上菜
@csrf_exempt
def delive_food(request):
    print("上菜请求")
    if request.method == "POST":
        order_id = request.POST.get("order_id")
        food_id = request.POST.get("food_id")
        print(order_id, food_id)
        OrderItem.objects.filter(orderID_id=order_id, foodID_id=food_id).update(status=3)
        try:
            return HttpResponse(json.dumps({
                'status': "OK"
            }))
        except:
            return HttpResponse(json.dumps({
                'status': "FAIL"
            }))


# 10后厨界面
@login_required
def food_supplier(request):
    return render(request, 'FoodSupplier.html')


# 11后厨接单或者呼叫上菜
@csrf_exempt
def cook(request):
    # 打印请求的路径（调试）
    print(request.path)
    # 判断请求的方法是否为POST
    if request.method == "POST":
        # 从POST数据中获取操作类型（'take_order'表示接单，其他值表示呼叫上菜）
        OP = request.POST.get("OP")
        # 从POST数据中获取订单ID
        order_id = int(request.POST.get("order_id"))
        # 从POST数据中获取菜品ID
        food_id = int(request.POST.get("food_id"))

        # 在数据库中查询与指定订单ID和菜品ID匹配的订单项
        orderItem = OrderItem.objects.filter(orderID_id=order_id, foodID_id=food_id)

        # 根据操作类型设置目标状态（1表示已接单，2表示已烹饪完成）
        target_status = 1 if OP == "take_order" else 2

        # 如果操作是接单，则更新订单项的状态为已接单，并记录开始烹饪时间
        if OP == "take_order":
            orderItem.update(status=target_status)
            orderItem.update(start_cook_time=datetime.datetime.now())
            # 如果操作不是接单（即呼叫上菜），则更新订单项的状态为已烹饪完成，并记录结束烹饪时间
        else:
            orderItem.update(status=target_status)
            orderItem.update(end_cook_time=datetime.datetime.now())
            # 注意：在Django中，使用update()方法时不需要再调用save()，因为它会立即执行数据库更新
        # 返回一个包含状态为'OK'的JSON响应给请求方
        return HttpResponse(json.dumps({'status': 'OK',
        }))


    # 辅助函数 数据库查询结果转换成 json/dict'''
def dictfetchall(cursor):
    columns = [col[0] for col in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]


# -------------管理功能 --------------
# 01订单管理
def orders(request):
    # 使用Django的ORM（对象关系映射）来查询数据库中的所有Order对象，并将它们存储在名为orders的变量中。
    orders = Order.objects.all()
    # 模板渲染，并将查询到的orders变量传递给模板
    return render(request, 'manage/orders.html', {
        'orders': orders,
    })

#  01-1订单查询
def order_list(request):
    order_id = request.GET.get('order_id')
    table_id = request.GET.get('table_id')

    # 初始化查询条件为空，即不进行任何过滤
    query = Q()

    # 如果提供了order_id，添加到查询条件中
    if order_id:
        query &= Q(ID=order_id)

        # 如果提供了table_id，也添加到查询条件中
    if table_id:
        query &= Q(table_id=table_id)

        # 使用Q对象进行过滤查询
    orders = Order.objects.filter(query)

    # 传递渲染
    context = {'orders': orders}
    return render(request, 'manage/orders.html', context)

# 02员工管理
@csrf_exempt
def staffs(request):
    if request.method == "GET":
        form = forms.StaffForm()
        staffs = Staff.objects.all()
        return render(request, 'manage/staffs.html', {
            'form': form,
            'staffs': staffs,
        })
    elif request.method == "POST":
        form_back = forms.StaffForm(request.POST)
        if form_back.is_valid(): #表单合法，保存员工数据
            form_back.save()
            return redirect('/manage/staffs')
        else:
            '''
            print(form_back.errors.as_data())
            print(form_back.errors.as_json())
            print(form_back.errors.as_text())
            print(form_back.errors.as_ul())
            '''
            return HttpResponse(json.dumps({
                'status': 'FAIL',
            }))


# 03餐位管理
@csrf_exempt
def tables(request):
    if request.method == "GET":
        print("get")
        form = forms.Staff_TableForm()
        tables = []
        staffs = []
        with connection.cursor() as cursor:
            SELECT_COL = ' distinct {0}_staff_table.ID table_id '
            SELECT_COL += ', {0}_staff_table.name table_name '
            SELECT_COL += ', {0}_staff.ID staff_id '
            SELECT_COL += ', {0}_staff.name staff_name '
            SELECT_COL = SELECT_COL.format('OrderSystem')

            SELECT_FROM = '{0}_staff_table, {0}_staff '
            SELECT_FROM = SELECT_FROM.format('OrderSystem')

            SELECT_WHERE = '{0}_staff.ID = {0}_staff_table.staff_id '
            SELECT_WHERE = SELECT_WHERE.format('OrderSystem')

            SELECT_SQL = f'select {SELECT_COL} from {SELECT_FROM} where {SELECT_WHERE}'
            cursor.execute(SELECT_SQL)

            tables = dictfetchall(cursor)

        with connection.cursor() as cursor:
            cursor.execute(
                'select ID staff_id, name staff_name from OrderSystem_staff;')
            staffs = dictfetchall(cursor)

        '''
        print(tables)
        '''

        return render(request, 'manage/tables.html', {
            'form': form,
            'tables': tables,
            'staffs': staffs,
        })

    elif request.method == "POST":
        print("post")
        form_back = forms.Staff_TableForm(request.POST)
        if form_back.is_valid():
            form_back.save()
            return redirect('/manage/tables')
        else:
            '''
            print(form_back.errors.as_data())
            print(form_back.errors.as_json())
            print(form_back.errors.as_text())
            print(form_back.errors.as_ul())
            '''
        return HttpResponse(json.dumps({
                'status': 'FAIL',
        }))


# 04菜品管理
@csrf_exempt
def foods(request):
    if request.method == "GET":
        # 获取所有菜品和菜品类型
        foods = Food.objects.all()
        food_types = Foodtype.objects.all()

        # 创建表单实例
        food_form = forms.FoodForm()
        food_type_form = forms.FoodtypeForm()

        # 渲染模板
        return render(request, 'manage/foods.html', {
            'food_form': food_form,
            'food_type_form': food_type_form,
            'foods': foods,
            'food_types': food_types,
        })

    elif request.method == "POST":
        # 验证菜品表单
        form_food = forms.FoodForm(request.POST)
        if form_food.is_valid():
            food = form_food.save(commit=False)  # 创建Food实例，但不保存

            # 处理图片上传
            if 'image' in request.FILES:
                image = request.FILES['image']
                fs = FileSystemStorage()
                filename = fs.save(image.name, image)
                uploaded_file_url = fs.url(filename)
                food.image = filename  # 将文件名保存到food实例的image字段

            food.save()  # 现在保存菜品到数据库

            return redirect('/manage/foods')  # 重定向回菜品列表

        # 验证菜品类型表单（注意：这里也处理了，但在实际应用中可能不需要同时处理）
        form_food_type = forms.FoodtypeForm(request.POST)
        if form_food_type.is_valid():
            form_food_type.save()  # 保存菜品类型
            return redirect('/manage/foods')  # 重定向回菜品列表

        # 如果两个表单都验证失败
        return HttpResponse(json.dumps({'status': 'FAIL'}))


# 05删除员工/菜品/餐位
@csrf_exempt
def dark(request):
    # 获取POST请求中的数据
    target = request.POST

    # 从POST数据中提取要操作的表名
    table = target['table']

    # 初始化SQL语句为空字符串
    SQL = ''

    # 判断是否要删除对象
    if target['double'] == 'false':     #如果double为false，则删除的对象是员工或者餐位
        # 提取要删除的员工的ID
        ID = target['id']
        # 构造删除整个记录的SQL语句
        SQL += f'delete from OrderSystem_{table} where ID={ID}'

    elif target['double'] == 'true':    #如果double为true，则删除的对象是菜品
        # 提取要删除的菜品ID和订单ID
        foodID_id = target['foodID_id']
        orderID_id = target['orderID_id']
        # 构造删除订单中特定菜品项的SQL语句
        SQL += f'delete from OrderSystem_{table} where foodID_id={foodID_id} and orderID_id={orderID_id}'

        print('========================================================================')
        print(SQL)
        print('========================================================================')
        try:
            # 使用Django的数据库连接执行SQL语句
            with connection.cursor() as cursor:
                cursor.execute(SQL)
            return HttpResponse(json.dumps({
                'status': 'OK',
            }))
        except:
            return HttpResponse(json.dumps({
                'status': 'FAIL',
            }))
